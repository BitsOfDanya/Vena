import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.bootstrap_ap_gain import paired_bootstrap
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--block", choices=("calendar_week", "channel"), default="calendar_week")
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), default=2025)
    parser.add_argument("--repeats", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    cache, _, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years=0)
    y = valid["target"].to_numpy()
    blend = 0.5 * (linear + tree)
    blocks = (
        valid["ts"].dt.to_period("W").astype(str).to_numpy()
        if args.block == "calendar_week" else valid["channel_id"].to_numpy()
    )
    differences = paired_bootstrap(y, (linear, blend), blocks, args.repeats, args.seed)
    print(json.dumps({
        "year": args.valid_year, "sensor": "fan", "baseline": "all_history_linear",
        "candidate": "all_history_blend_50", "block": args.block,
        "seed": args.seed, "repeats": len(differences),
        "n_candidates": len(y), "n_positive": int(y.sum()),
        "baseline_ap": float(average_precision_score(y, linear)),
        "candidate_ap": float(average_precision_score(y, blend)),
        "ap_gain_ci95": np.quantile(differences, [0.025, 0.975]).tolist(),
        "fraction_positive_gain": float((differences > 0).mean()),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
