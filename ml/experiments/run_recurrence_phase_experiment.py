import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

PHASE_COLUMNS = (
    "elapsed_to_median_failure_gap",
    "days_past_median_failure_gap",
    "standardized_failure_gap",
)


def attach_phase(frame):
    result = frame.copy()
    elapsed = result["time_since_last_failure_days"].to_numpy()
    median = result["median_time_between_failures_days"].to_numpy()
    std = result["std_inter_failure_interval_days"].to_numpy()
    known = (elapsed >= 0) & (median > 0)
    result[PHASE_COLUMNS[0]] = np.where(known, np.clip(elapsed / np.maximum(median, 1), 0, 20), -1)
    result[PHASE_COLUMNS[1]] = np.where(known, np.clip(elapsed - median, -365, 365), -1)
    result[PHASE_COLUMNS[2]] = np.where(
        known & (std > 0), np.clip((elapsed - median) / np.maximum(std, 1), -20, 20), -1,
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--sensor", choices=("pump", "fan"), default="pump")
    parser.add_argument("--variants", default="base,phase")
    parser.add_argument("--frozen-from")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {row["variant"]: row for row in map(json.loads, source)}
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = attach_phase(pd.read_parquet(cache))
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    if args.sensor == "pump":
        train &= frame["ts"].dt.year >= args.valid_year - 3
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    for variant in args.variants.split(","):
        if variant not in ("base", "phase"):
            raise ValueError(variant)
        tick = time.monotonic()
        columns = training.feature_columns()
        if variant == "phase":
            columns.extend(PHASE_COLUMNS)
        x_train = train_frame[columns]
        x_valid = valid_frame[columns]
        linear = LogisticRegressionModel().fit(x_train, train_frame["target"])
        tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
            x_train, train_frame["target"],
        )
        score = (linear.predict_proba(x_valid) + tree.predict_proba(x_valid)) / 2
        metrics = frontier_metrics(y_valid, score)
        h1 = valid_frame["ts"].dt.month.to_numpy() <= 6
        metrics.update({
            "variant": variant, "sensor": args.sensor, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(y_valid.sum()),
            "half_ap": {
                "h1": float(average_precision_score(y_valid[h1], score[h1])) if h1.any() else None,
                "h2": float(average_precision_score(y_valid[~h1], score[~h1])) if (~h1).any() else None,
            },
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "seconds": round(time.monotonic() - tick, 1),
        })
        if variant in frozen and frozen[variant]["threshold_p70"] is not None:
            metrics["frozen_from_year"] = frozen[variant]["valid_year"]
            metrics["at_frozen_p70"] = eval_at_threshold(
                y_valid, score, frozen[variant]["threshold_p70"],
            )
        emit(metrics)


if __name__ == "__main__":
    main()
