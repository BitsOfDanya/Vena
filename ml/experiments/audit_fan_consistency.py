"""Summarize fan blend gains across channels and calendar weeks."""

import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths


def summarize_groups(labels, baseline, blend, group_values, min_rows):
    """Report distribution of within-group AP changes, never group IDs."""
    groups = pd.Series(group_values).groupby(group_values, sort=False).indices
    differences = []
    sizes = []
    for rows in groups.values():
        local_labels = labels[rows]
        if len(rows) < min_rows or local_labels.sum() == 0 or local_labels.sum() == len(rows):
            continue
        differences.append(
            average_precision_score(local_labels, blend[rows])
            - average_precision_score(local_labels, baseline[rows])
        )
        sizes.append(len(rows))
    differences = np.asarray(differences)
    sizes = np.asarray(sizes)
    return {
        "n_groups": len(differences),
        "n_positive_gain": int((differences > 0).sum()),
        "n_negative_gain": int((differences < 0).sum()),
        "median_ap_gain": float(np.median(differences)) if len(differences) else None,
        "p25_ap_gain": float(np.quantile(differences, 0.25)) if len(differences) else None,
        "p75_ap_gain": float(np.quantile(differences, 0.75)) if len(differences) else None,
        "candidate_weighted_mean_ap_gain": (
            float(np.average(differences, weights=sizes)) if len(differences) else None
        ),
    }


def main():
    """Evaluate a single year without exposing channel or week identifiers."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    args = parser.parse_args()
    cache, _, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years=0)
    y = valid["target"].to_numpy()
    blend = (linear + tree) / 2
    groups = {
        "channel": (valid["channel_id"].to_numpy(), 50),
        "calendar_week": (valid["ts"].dt.to_period("W").astype(str).to_numpy(), 50),
    }
    for name, (group_values, min_rows) in groups.items():
        result = summarize_groups(y, linear, blend, group_values, min_rows)
        result.update({"sensor": "fan", "year": args.valid_year, "grouping": name})
        emit(result)


if __name__ == "__main__":
    main()
