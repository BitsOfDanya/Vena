"""Compare a small regularized LightGBM grid on 2024 temporal halves."""

import argparse
import json
import time

import pandas as pd
from lightgbm import LGBMClassifier

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

GRID = (
    ("base", 7, 500, 300, 0.08),
    ("leaf200", 7, 200, 300, 0.08),
    ("leaf1000", 7, 1000, 300, 0.08),
    ("leaves15", 15, 500, 300, 0.08),
    ("leaves15_leaf1000", 15, 1000, 300, 0.08),
    ("slow600", 7, 500, 600, 0.04),
    ("short150", 7, 500, 150, 0.08),
    ("long500", 7, 500, 500, 0.08),
)


def slice_metrics(frame, score):
    """Report AP and recall at candidate precision 0.70 for each half-year."""
    months = frame["ts"].dt.month.to_numpy()
    masks = {"full": months > 0, "h1": months <= 6, "h2": months > 6}
    result = {}
    for name, mask in masks.items():
        if not mask.any():
            result[name] = None
            continue
        labels = frame.loc[mask, "target"]
        metrics = frontier_metrics(labels, score[mask])
        result[name] = {
            "n": int(mask.sum()), "n_positive": int(labels.sum()),
            "ap": float(metrics["pr_auc"]),
            "recall_at_p70": float(metrics["recall_at_precision_0.7"]),
        }
    return result


def main():
    """Fit shared logistic component and one tree per grid point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--variants", default=",".join(row[0] for row in GRID))
    parser.add_argument("--operational", action="store_true")
    parser.add_argument("--frozen-from")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {row["variant"]: row for row in map(json.loads, source)}
    chosen = set(args.variants.split(","))
    unknown = chosen - {row[0] for row in GRID}
    if unknown:
        raise ValueError(f"Unknown grid variants: {sorted(unknown)}")
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache) if args.operational else None
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    cols = training.feature_columns()
    x_train = train_frame[cols]
    x_valid = valid_frame[cols]
    y_train = train_frame["target"]
    linear = LogisticRegressionModel().fit(x_train, y_train)
    linear_score = linear.predict_proba(x_valid)
    for name, leaves, min_child, n_estimators, learning_rate in GRID:
        if name not in chosen:
            continue
        tick = time.monotonic()
        tree = LGBMClassifier(
            n_estimators=n_estimators, learning_rate=learning_rate,
            num_leaves=leaves, min_child_samples=min_child,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            class_weight="balanced", random_state=42, n_jobs=6, verbose=-1,
        )
        tree.fit(x_train.fillna(-1), y_train)
        tree_score = tree.predict_proba(x_valid.fillna(-1))[:, 1]
        blend = 0.5 * (linear_score + tree_score)
        result = {
            "valid_year": args.valid_year, "variant": name,
            "num_leaves": leaves, "min_child_samples": min_child,
            "n_estimators": n_estimators, "learning_rate": learning_rate,
            "n_train": len(train_frame),
            "tree": slice_metrics(valid_frame, tree_score),
            "blend": slice_metrics(valid_frame, blend),
            "threshold_p70": threshold_at_precision(valid_frame["target"], blend),
            "seconds": round(time.monotonic() - tick, 1),
        }
        if episodes is not None:
            result["operational"] = operational_summary(valid_frame, blend, episodes)
        if name in frozen and frozen[name]["threshold_p70"] is not None:
            result["frozen_from_year"] = frozen[name]["valid_year"]
            result["at_frozen_p70"] = eval_at_threshold(
                valid_frame["target"], blend, frozen[name]["threshold_p70"],
            )
        emit(result)


if __name__ == "__main__":
    main()
