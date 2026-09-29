import argparse
import time

import numpy as np
import pandas as pd

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

EVENT_CACHES = {
    "pump": "analysis/ml_ready/cache/events_Состояние_насоса.parquet",
    "fan": "analysis/ml_ready/cache/events_Состояние_вентилятора.parquet",
}


def attach_prior_state(frame, sensor):
    events = pd.read_parquet(EVENT_CACHES[sensor], columns=["channel_id", "ts", "raw_value"])
    result = frame.copy()
    states = np.full(len(result), "missing", dtype=object)
    events_by_channel = {
        channel_id: group.sort_values("ts", kind="stable")
        for channel_id, group in events.groupby("channel_id", sort=False, observed=True)
    }
    for channel_id, candidates in result.groupby("channel_id", sort=False, observed=True):
        channel_events = events_by_channel.get(channel_id)
        if channel_events is None:
            continue
        times = channel_events["ts"].to_numpy()
        values = channel_events["raw_value"].to_numpy()
        positions = np.searchsorted(times, candidates["ts"].to_numpy(), side="left") - 1
        valid = positions >= 0
        states[candidates.index.to_numpy()[valid]] = values[positions[valid]]
    result["prior_state"] = states
    return result


def model_frame(frame, columns, state_columns):
    x = frame[columns]
    if not state_columns:
        return x
    flags = pd.get_dummies(frame["prior_state"], prefix="prior_state", dtype=float)
    flags = flags.reindex(columns=state_columns, fill_value=0)
    return pd.concat([x, flags], axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--sensor", choices=tuple(EVENT_CACHES), default="pump")
    parser.add_argument("--window-years", type=int, choices=(0, 1, 3), default=3)
    parser.add_argument("--variants", default="base,prior_state")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = attach_prior_state(pd.read_parquet(cache).reset_index(drop=True), args.sensor)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    if args.window_years:
        train &= frame["ts"].dt.year >= args.valid_year - args.window_years
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    columns = training.feature_columns()
    state_columns = [f"prior_state_{value}" for value in sorted(train_frame["prior_state"].unique())]
    for variant in args.variants.split(","):
        if variant not in ("base", "prior_state"):
            raise ValueError(variant)
        tick = time.monotonic()
        fixed = state_columns if variant == "prior_state" else []
        x_train = model_frame(train_frame, columns, fixed)
        x_valid = model_frame(valid_frame, columns, fixed)
        linear = LogisticRegressionModel().fit(x_train, train_frame["target"])
        tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
            x_train, train_frame["target"],
        )
        score = (linear.predict_proba(x_valid) + tree.predict_proba(x_valid)) / 2
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "variant": variant, "sensor": args.sensor, "valid_year": args.valid_year,
            "window_years": args.window_years,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(y_valid.sum()),
            "n_state_categories": len(fixed),
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "seconds": round(time.monotonic() - tick, 1),
        })
        emit(metrics)


if __name__ == "__main__":
    main()
