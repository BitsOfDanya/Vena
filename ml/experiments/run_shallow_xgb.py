import argparse
import json
import time

import pandas as pd
from xgboost import XGBClassifier

from experiments.common import emit, threshold_at_precision, validation_mask
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics
from pipeline.models import LogisticRegressionModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--weights", default="0,0.25,0.5,0.75,1")
    parser.add_argument("--frozen-from")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {row["xgb_weight"]: row["threshold_p70"] for row in map(json.loads, source)}
    cache, _, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (
        frame["ts"].dt.year >= args.valid_year - 3
    )
    valid = validation_mask(frame, args.valid_year)
    columns = training.feature_columns()
    x_train = frame.loc[train, columns].fillna(-1)
    y_train = frame.loc[train, "target"]
    x_valid = frame.loc[valid, columns].fillna(-1)
    y_valid = frame.loc[valid, "target"]
    start_fit = time.monotonic()
    linear = LogisticRegressionModel().fit(x_train, y_train)
    linear_score = linear.predict_proba(x_valid)
    positive_weight = (len(y_train) - int(y_train.sum())) / max(int(y_train.sum()), 1)
    tree = XGBClassifier(
        n_estimators=300, learning_rate=0.05, max_depth=2,
        min_child_weight=100, reg_lambda=10, subsample=0.8,
        colsample_bytree=0.8, tree_method="hist", max_bin=255,
        scale_pos_weight=positive_weight, eval_metric="aucpr",
        objective="binary:logistic", random_state=42, n_jobs=6,
    )
    tree.fit(x_train, y_train)
    tree_score = tree.predict_proba(x_valid)[:, 1]
    fit_seconds = round(time.monotonic() - start_fit, 1)
    for weight in map(float, args.weights.split(",")):
        score = (1 - weight) * linear_score + weight * tree_score
        quality = frontier_metrics(y_valid, score)
        result = {
            "valid_year": args.valid_year,
            "xgb_weight": weight,
            "n_train": int(train.sum()), "n_valid": int(valid.sum()),
            "ap": quality["pr_auc"],
            "recall_at_p70": quality["recall_at_precision_0.7"],
            "precision_at_r50": quality["precision_at_recall_0.5"],
            "threshold_p70": threshold_at_precision(y_valid, score),
            "fit_score_seconds": fit_seconds,
        }
        if weight in frozen and frozen[weight] is not None:
            safe = valid["ts"].to_numpy() >= pd.Timestamp(f"{args.valid_year}-01-04").to_datetime64()
            result["at_previous_p70"] = eval_at_threshold(
                y_valid.to_numpy()[safe], score[safe], frozen[weight],
            )
        emit(result)


if __name__ == "__main__":
    main()
