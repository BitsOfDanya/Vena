import argparse
import time

import pandas as pd

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import episodes as episodes_mod
from pipeline import training
from pipeline.formal.metrics import frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    target24 = episodes_mod.assign_targets(
        frame[["channel_id", "ts"]], episodes, horizon_hours=24,
    )["target"].to_numpy()
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    columns = training.feature_columns()
    x_train = train_frame[columns]
    x_valid = valid_frame[columns]
    tick = time.monotonic()
    linear72 = LogisticRegressionModel().fit(x_train, train_frame["target"])
    tree72 = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
        x_train, train_frame["target"],
    )
    tree24 = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
        x_train, target24[train],
    )
    base = 0.5 * (linear72.predict_proba(x_valid) + tree72.predict_proba(x_valid))
    score24 = tree24.predict_proba(x_valid)
    fit_seconds = round(time.monotonic() - tick, 1)
    for weight in (0.0, 0.25, 0.5, 0.75, 1.0):
        score = (1 - weight) * base + weight * score24
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "weight_24h": weight, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_train_24h_positive": int(target24[train].sum()),
            "n_valid": len(valid_frame), "n_positive": int(y_valid.sum()),
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "fit_score_seconds": fit_seconds,
        })
        emit(metrics)


if __name__ == "__main__":
    main()
