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
from experiments.run_recurrence_phase_experiment import PHASE_COLUMNS, attach_phase
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel


def fit_blend(train_frame, valid_frame, columns):
    linear = LogisticRegressionModel().fit(train_frame[columns], train_frame["target"])
    tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
        train_frame[columns], train_frame["target"],
    )
    return (linear.predict_proba(valid_frame[columns]) + tree.predict_proba(valid_frame[columns])) / 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--frozen-from")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {row["variant"]: row for row in map(json.loads, source)}
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = attach_phase(pd.read_parquet(cache))
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    tick = time.monotonic()
    columns = training.feature_columns()
    base = fit_blend(train_frame, valid_frame, columns)
    phase = fit_blend(train_frame, valid_frame, columns + list(PHASE_COLUMNS))
    h1 = valid_frame["ts"].dt.month.to_numpy() <= 6
    scores = {
        "base": base,
        "phase": phase,
        "phase_h1": np.where(h1, phase, base),
    }
    fit_seconds = round(time.monotonic() - tick, 1)
    for name, score in scores.items():
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "variant": name, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(y_valid.sum()),
            "half_ap": {
                "h1": float(average_precision_score(y_valid[h1], score[h1])) if h1.any() else None,
                "h2": float(average_precision_score(y_valid[~h1], score[~h1])) if (~h1).any() else None,
            },
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "fit_seconds": fit_seconds,
        })
        if name in frozen and frozen[name]["threshold_p70"] is not None:
            metrics["frozen_from_year"] = frozen[name]["valid_year"]
            metrics["at_frozen_p70"] = eval_at_threshold(
                y_valid, score, frozen[name]["threshold_p70"],
            )
        emit(metrics)


if __name__ == "__main__":
    main()
