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
STATES = {
    "on": "Включен", "off": "Выключен", "normal": "Норма",
    "unknown": "Неопределен", "unpowered": "Обесточен",
    "flooded": "Затоплен", "all_pumps": "Работают все насосы в АНС",
    "device_off": "Отключено устройство",
}
WINDOWS = {"24h": np.timedelta64(24, "h"), "7d": np.timedelta64(7, "D")}


def attach_state_counts(frame, sensor):
    events = pd.read_parquet(EVENT_CACHES[sensor], columns=["channel_id", "ts", "raw_value"])
    by_channel = {
        cid: group.sort_values("ts", kind="stable")
        for cid, group in events.groupby("channel_id", sort=False, observed=True)
    }
    result = frame.copy()
    feature_arrays = {
        f"state_{code}_{window}": np.zeros(len(result), dtype=np.float32)
        for code in STATES for window in WINDOWS
    }
    for cid, candidates in result.groupby("channel_id", sort=False, observed=True):
        group = by_channel.get(cid)
        if group is None:
            continue
        event_times = group["ts"].to_numpy()
        event_states = group["raw_value"].to_numpy()
        candidate_times = candidates["ts"].to_numpy()
        row_indices = candidates.index.to_numpy()
        hi = np.searchsorted(event_times, candidate_times, side="left")
        for window_name, window_size in WINDOWS.items():
            lo = np.searchsorted(event_times, candidate_times - window_size, side="left")
            for code, state in STATES.items():
                counts = np.cumsum(event_states == state, dtype=np.int64)
                counts = np.concatenate([[0], counts])
                feature_arrays[f"state_{code}_{window_name}"][row_indices] = counts[hi] - counts[lo]
    for name, values in feature_arrays.items():
        result[name] = values
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--sensor", choices=tuple(EVENT_CACHES), default="pump")
    parser.add_argument("--window-years", type=int, choices=(0, 1, 3), default=3)
    parser.add_argument("--variants", default="base,state_counts")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = attach_state_counts(pd.read_parquet(cache).reset_index(drop=True), args.sensor)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    if args.window_years:
        train &= frame["ts"].dt.year >= args.valid_year - args.window_years
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    labels = valid_frame["target"].to_numpy()
    for variant in args.variants.split(","):
        if variant not in ("base", "state_counts"):
            raise ValueError(variant)
        tick = time.monotonic()
        columns = training.feature_columns()
        if variant == "state_counts":
            columns.extend(f"state_{code}_{window}" for code in STATES for window in WINDOWS)
        x_train = train_frame[columns]
        x_valid = valid_frame[columns]
        linear = LogisticRegressionModel().fit(x_train, train_frame["target"])
        tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
            x_train, train_frame["target"],
        )
        score = (linear.predict_proba(x_valid) + tree.predict_proba(x_valid)) / 2
        metrics = frontier_metrics(labels, score)
        metrics.update({
            "variant": variant, "sensor": args.sensor,
            "window_years": args.window_years, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(labels.sum()),
            "threshold_p70": threshold_at_precision(labels, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "seconds": round(time.monotonic() - tick, 1),
        })
        emit(metrics)


if __name__ == "__main__":
    main()
