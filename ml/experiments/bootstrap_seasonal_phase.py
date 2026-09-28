"""Block uncertainty for the 2025 first-half recurrence-phase policy."""

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.run_recency_experiment import cache_paths
from experiments.run_recurrence_phase_experiment import PHASE_COLUMNS, attach_phase
from experiments.run_seasonal_phase_gate import fit_blend
from pipeline import training


def precision_recall(y, score, threshold):
    """Compute candidate precision and recall at an unchanged threshold."""
    selected = score >= threshold
    tp = (selected & (y == 1)).sum()
    return tp / max(selected.sum(), 1), tp / max((y == 1).sum(), 1)


def main():
    """Emit aggregate paired intervals over full weeks or channels."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", choices=("calendar_week", "channel"), default="calendar_week")
    parser.add_argument("--repeats", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    cache, _, _ = cache_paths("pump", False)
    frame = attach_phase(pd.read_parquet(cache))
    start = pd.Timestamp("2025-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= 2022)
    # The 2024 threshold labels can use the first 72 hours of 2025.
    full_valid = frame["ts"].dt.year == 2025
    valid = full_valid & (frame["ts"] >= start + pd.Timedelta(hours=72))
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    columns = training.feature_columns()
    base = fit_blend(train_frame, valid_frame, columns)
    phase = fit_blend(train_frame, valid_frame, columns + list(PHASE_COLUMNS))
    h1 = valid_frame["ts"].dt.month.to_numpy() <= 6
    candidate = np.where(h1, phase, base)
    y = valid_frame["target"].to_numpy()
    blocks = (
        valid_frame["ts"].dt.to_period("W").astype(str).to_numpy()
        if args.block == "calendar_week" else valid_frame["channel_id"].to_numpy()
    )
    _, inverse = np.unique(blocks, return_inverse=True)
    groups = [np.flatnonzero(inverse == group) for group in range(inverse.max() + 1)]
    random = np.random.default_rng(args.seed)
    thresholds = (0.7572332851137136, 0.7576914851265073)
    differences = []
    for _ in range(args.repeats):
        sampled = random.integers(0, len(groups), len(groups))
        rows = np.concatenate([groups[group] for group in sampled])
        if not y[rows].any():
            continue
        base_p, base_r = precision_recall(y[rows], base[rows], thresholds[0])
        cand_p, cand_r = precision_recall(y[rows], candidate[rows], thresholds[1])
        differences.append([
            average_precision_score(y[rows], candidate[rows])
            - average_precision_score(y[rows], base[rows]),
            cand_p - base_p, cand_r - base_r,
        ])
    differences = np.asarray(differences)
    print(json.dumps({
        "year": 2025, "candidate": "phase_h1", "baseline": "base",
        "block": args.block, "seed": args.seed, "repeats": len(differences),
        "n_candidates": len(y), "n_positive": int(y.sum()),
        "excluded_first_72h": int((full_valid & ~valid).sum()),
        "ap_gain": float(average_precision_score(y, candidate) - average_precision_score(y, base)),
        "ap_gain_ci95": np.quantile(differences[:, 0], [0.025, 0.975]).tolist(),
        "precision_gain_ci95": np.quantile(differences[:, 1], [0.025, 0.975]).tolist(),
        "recall_gain_ci95": np.quantile(differences[:, 2], [0.025, 0.975]).tolist(),
        "fraction_positive_ap_gain": float((differences[:, 0] > 0).mean()),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
