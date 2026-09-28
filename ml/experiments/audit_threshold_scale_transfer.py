"""Test unlabeled train-score scale adjustment of yearly fan thresholds."""

import argparse
import json

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from experiments.common import threshold_at_precision, validation_mask
from experiments.run_blend_experiment import fit_models
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold


def yearly_scores(frame, year):
    """Fit only before a year and score train plus future holdout."""
    start = pd.Timestamp(f"{year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    valid = validation_mask(frame, year)
    linear, tree = fit_models(frame, year, window_years=0)
    columns = training.feature_columns()

    def score(mask):
        x = frame.loc[mask, columns]
        return 0.5 * (linear.predict_proba(x) + tree.predict_proba(x))

    return {
        "train": score(train),
        "valid": score(valid),
        "frame": frame.loc[valid, ["ts", "target"]],
    }


def score_quantiles(values):
    """Summarize score scale without retaining candidate-level output."""
    return {
        "p50": float(np.quantile(values, 0.5)),
        "p90": float(np.quantile(values, 0.9)),
        "p99": float(np.quantile(values, 0.99)),
        "p999": float(np.quantile(values, 0.999)),
    }


def main():
    """Compare raw, train-quantile and train-median threshold transfer."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("fan",), default="fan")
    args = parser.parse_args()
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    previous = yearly_scores(frame, 2024)
    for year in (2025, 2026):
        current = yearly_scores(frame, year)
        prev_labels = previous["frame"]["target"].to_numpy()
        threshold = threshold_at_precision(prev_labels, previous["valid"])
        quantile = float((previous["train"] <= threshold).mean())
        current_quantile_threshold = float(np.quantile(current["train"], quantile))
        clip = lambda values: np.clip(values, 1e-6, 1 - 1e-6)
        logit_shift = float(np.median(logit(clip(current["train"])))
                            - np.median(logit(clip(previous["train"]))))
        median_shift_threshold = float(expit(logit(clip(threshold)) + logit_shift))
        labels = current["frame"]["target"].to_numpy()
        cutoff = pd.Timestamp(f"{year}-01-01") + pd.Timedelta(hours=72)
        safe = (current["frame"]["ts"] >= cutoff).to_numpy()
        variants = {
            "raw_previous_threshold": threshold,
            "train_quantile_transfer": current_quantile_threshold,
            "train_median_logit_shift": median_shift_threshold,
        }
        print(json.dumps({
            "sensor": args.sensor, "valid_year": year,
            "previous_year": year - 1, "prior_train_quantile": quantile,
            "train_median_logit_shift": logit_shift,
            "n_valid": len(labels), "n_positive": int(labels.sum()),
            "positive_rate": float(labels.mean()),
            "n_boundary_disjoint": int(safe.sum()),
            "previous_train_score": score_quantiles(previous["train"]),
            "current_train_score": score_quantiles(current["train"]),
            "current_valid_score": score_quantiles(current["valid"]),
            "boundary_disjoint": {
                name: eval_at_threshold(labels[safe], current["valid"][safe], value)
                for name, value in variants.items()
            },
        }, ensure_ascii=False))
        previous = current


if __name__ == "__main__":
    main()
