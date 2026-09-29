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
from pipeline import candidates, training
from pipeline.formal.metrics import frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel


def trigger_features(frame, enabled):
    columns = training.feature_columns()
    if not enabled:
        return frame[columns]
    flags = pd.get_dummies(frame["trigger"], prefix="trigger", dtype=float)
    wanted = [f"trigger_{name}" for name in candidates.TRIGGER_TYPES]
    flags = flags.reindex(columns=wanted, fill_value=0)
    return pd.concat([frame[columns], flags], axis=1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--variants", default="base,trigger")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    y_valid = valid_frame["target"].to_numpy()
    for variant in args.variants.split(","):
        if variant not in ("base", "trigger"):
            raise ValueError(variant)
        tick = time.monotonic()
        x_train = trigger_features(train_frame, variant == "trigger")
        x_valid = trigger_features(valid_frame, variant == "trigger")
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
