"""Test the known observation age of a pump channel as a causal feature."""

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

EVENT_CACHE = "analysis/ml_ready/cache/events_Состояние_насоса.parquet"


def attach_channel_age(frame):
    """Measure days since the first observed event, using no future events."""
    events = pd.read_parquet(EVENT_CACHE, columns=["channel_id", "ts"])
    first = events.groupby("channel_id", observed=True)["ts"].min()
    age_days = (frame["ts"] - frame["channel_id"].map(first)).dt.total_seconds() / 86400
    if age_days.isna().any() or (age_days < 0).any():
        raise ValueError("Channel observation age is missing or negative")
    frame = frame.copy()
    frame["log_channel_age_days"] = np.log1p(age_days)
    return frame


def main():
    """Evaluate a predeclared age feature against the fixed blend."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--variants", default="base,age")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = attach_channel_age(pd.read_parquet(cache))
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    for variant in args.variants.split(","):
        if variant not in ("base", "age"):
            raise ValueError(variant)
        tick = time.monotonic()
        columns = training.feature_columns()
        if variant == "age":
            columns.append("log_channel_age_days")
        x_train = train_frame[columns]
        x_valid = valid_frame[columns]
        linear = LogisticRegressionModel().fit(x_train, train_frame["target"])
        tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
            x_train, train_frame["target"],
        )
        score = (linear.predict_proba(x_valid) + tree.predict_proba(x_valid)) / 2
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "variant": variant, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(y_valid.sum()),
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "seconds": round(time.monotonic() - tick, 1),
        })
        emit(metrics)


if __name__ == "__main__":
    main()
