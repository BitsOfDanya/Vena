"""Retrospective 2022-2023 check of fixed pump/fan model families."""

import argparse

import numpy as np
import pandas as pd

from experiments.common import emit, threshold_at_precision
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics


def main():
    """Train chronologically and transfer each 2022 threshold to 2023."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("pump", "fan"), required=True)
    args = parser.parse_args()
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    window = 3 if args.sensor == "pump" else 0
    previous = {}
    for year in (2022, 2023):
        valid, (linear, tree), seconds = fit_scores(frame, year, window)
        labels = valid["target"].to_numpy()
        scores = {"linear": linear, "blend": (linear + tree) / 2}
        for name, score in scores.items():
            quality = frontier_metrics(labels, score)
            threshold = threshold_at_precision(labels, score)
            result = {
                "sensor": args.sensor, "valid_year": year,
                "model": name, "n_valid": len(labels),
                "n_positive": int(labels.sum()),
                "ap": quality["pr_auc"],
                "recall_at_p70": quality["recall_at_precision_0.7"],
                "precision_at_r50": quality["precision_at_recall_0.5"],
                "threshold_p70": threshold,
                "score_median": float(np.median(score)),
                "fit_score_seconds": seconds,
            }
            if name in previous and previous[name] is not None:
                # Prior-year labels can extend 72 hours into this year.
                safe = valid["ts"].to_numpy() >= np.datetime64(f"{year}-01-04")
                result["n_transfer_rows"] = int(safe.sum())
                result["at_previous_p70"] = eval_at_threshold(
                    labels[safe], score[safe], previous[name],
                )
            emit(result)
            previous[name] = threshold


if __name__ == "__main__":
    main()
