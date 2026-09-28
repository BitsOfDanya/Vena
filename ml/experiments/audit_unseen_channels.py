"""Audit ranking on pump channels held out from supervised training."""

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import chronological_masks
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel
from pipeline.training import feature_columns


def score_models(frame, train_mask, valid_mask):
    """Fit the fixed baseline and recent-window blend on other channels."""
    columns = feature_columns()
    x_valid = frame.loc[valid_mask, columns]
    baseline = LogisticRegressionModel().fit(
        frame.loc[train_mask, columns], frame.loc[train_mask, "target"],
    )
    recent = train_mask & (frame["ts"].dt.year >= 2021)
    linear = LogisticRegressionModel().fit(
        frame.loc[recent, columns], frame.loc[recent, "target"],
    )
    tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
        frame.loc[recent, columns], frame.loc[recent, "target"],
    )
    baseline_score = baseline.predict_proba(x_valid)
    blend_score = 0.5 * linear.predict_proba(x_valid) + 0.5 * tree.predict_proba(x_valid)
    return baseline_score, blend_score


def main():
    """Emit only aggregate AP for a reproducible channel group holdout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fraction", type=float, default=0.2)
    args = parser.parse_args()
    if not 0 < args.fraction < 1:
        raise ValueError("fraction must be between zero and one")

    frame = pd.read_parquet("analysis/ml_ready/pump72_features.parquet")
    train, valid = chronological_masks(frame, 2024)
    channels = np.sort(frame.loc[valid, "channel_id"].unique())
    random = np.random.default_rng(args.seed)
    held = set(random.choice(channels, round(len(channels) * args.fraction), replace=False))
    train &= ~frame["channel_id"].isin(held)
    selected = valid & frame["channel_id"].isin(held)
    baseline_score, blend_score = score_models(frame, train, selected)
    labels = frame.loc[selected, "target"].to_numpy()
    print(json.dumps({
        "year": 2024, "seed": args.seed,
        "group": "channels_excluded_from_supervised_training",
        "n_channels": len(held), "n_candidates": len(labels),
        "n_positive": int(labels.sum()),
        "baseline_ap": average_precision_score(labels, baseline_score),
        "blend_ap": average_precision_score(labels, blend_score),
    }))


if __name__ == "__main__":
    main()
