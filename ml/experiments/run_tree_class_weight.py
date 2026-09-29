import argparse
import json
import time

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier

from experiments.common import emit, threshold_at_precision, validation_mask
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics
from pipeline.models import LogisticRegressionModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("pump", "fan"), required=True)
    parser.add_argument("--valid-year", type=int, choices=(2022, 2023, 2024, 2025, 2026), required=True)
    parser.add_argument("--frozen-from", help="JSONL thresholds selected in the previous year")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {
                (row["class_weight"], row["score_kind"]): row["threshold_p70"]
                for row in map(json.loads, source)
            }
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    if args.sensor == "pump":
        train &= frame["ts"].dt.year >= args.valid_year - 3
    valid = validation_mask(frame, args.valid_year)
    cols = training.feature_columns()
    x_train = frame.loc[train, cols].fillna(-1)
    y_train = frame.loc[train, "target"]
    x_valid = frame.loc[valid, cols].fillna(-1)
    y_valid = frame.loc[valid, "target"]
    linear = LogisticRegressionModel().fit(x_train, y_train)
    linear_score = linear.predict_proba(x_valid)
    for weight in ("balanced", None):
        tick = time.monotonic()
        tree = LGBMClassifier(
            n_estimators=300, learning_rate=0.08, num_leaves=7,
            min_child_samples=500, subsample=0.8, subsample_freq=1,
            colsample_bytree=0.8, class_weight=weight,
            random_state=42, n_jobs=6, verbose=-1,
        )
        tree.fit(x_train, y_train)
        tree_score = tree.predict_proba(x_valid)[:, 1]
        blend_score = (linear_score + tree_score) / 2
        variants = (
            ("tree", tree_score),
            ("blend", blend_score),
            ("blend_tree25", 0.75 * linear_score + 0.25 * tree_score),
            ("blend_tree75", 0.25 * linear_score + 0.75 * tree_score),
        )
        for kind, score in variants:
            quality = frontier_metrics(y_valid, score)
            result = {
                "sensor": args.sensor, "valid_year": args.valid_year,
                "class_weight": weight, "score_kind": kind,
                "n_train": int(train.sum()), "n_valid": int(valid.sum()),
                "ap": quality["pr_auc"],
                "recall_at_p70": quality["recall_at_precision_0.7"],
                "precision_at_r50": quality["precision_at_recall_0.5"],
                "threshold_p70": threshold_at_precision(y_valid, score),
                "score_median": float(np.median(score)),
                "fit_seconds": round(time.monotonic() - tick, 1),
            }
            previous_threshold = frozen.get((weight, kind))
            if previous_threshold is not None:
                result["at_frozen_p70"] = eval_at_threshold(y_valid, score, previous_threshold)
            emit(result)


if __name__ == "__main__":
    main()
