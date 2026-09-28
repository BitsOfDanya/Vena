"""Estimate paired block intervals for the 2025 pump AP improvement."""

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths, fit_and_score


def paired_bootstrap(y, scores, blocks, repeats, seed):
    """Resample whole weeks or channels, preserving candidate dependence."""
    baseline, candidate = scores
    _, inverse = np.unique(blocks, return_inverse=True)
    groups = [np.flatnonzero(inverse == group) for group in range(inverse.max() + 1)]
    random = np.random.default_rng(seed)
    differences = []
    for _ in range(repeats):
        sampled = random.integers(0, len(groups), len(groups))
        rows = np.concatenate([groups[group] for group in sampled])
        if y[rows].sum() == 0:
            continue
        differences.append(
            average_precision_score(y[rows], candidate[rows])
            - average_precision_score(y[rows], baseline[rows])
        )
    return np.asarray(differences)


def main():
    """Fit the fixed 2025 candidates and emit only aggregate bootstrap results."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--block", choices=("calendar_week", "channel"), default="calendar_week")
    args = parser.parse_args()

    cache, _, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    _, baseline_score = fit_and_score(frame, 2025, "baseline", 168)
    valid_frame, (linear_score, tree_score), _ = fit_scores(frame, 2025)
    candidate_score = 0.5 * linear_score + 0.5 * tree_score
    y = valid_frame["target"].to_numpy()
    blocks = (
        valid_frame["ts"].dt.to_period("W").astype(str).to_numpy()
        if args.block == "calendar_week" else valid_frame["channel_id"].to_numpy()
    )
    differences = paired_bootstrap(y, (baseline_score, candidate_score), blocks,
                                   args.repeats, args.seed)
    result = {
        "year": 2025,
        "block": args.block,
        "seed": args.seed,
        "repeats": len(differences),
        "n_candidates": len(y),
        "n_positive": int(y.sum()),
        "baseline_ap": average_precision_score(y, baseline_score),
        "candidate_ap": average_precision_score(y, candidate_score),
        "ap_gain": average_precision_score(y, candidate_score)
        - average_precision_score(y, baseline_score),
        "ap_gain_ci95": np.quantile(differences, [0.025, 0.975]).tolist(),
        "fraction_positive_gain": float((differences > 0).mean()),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
