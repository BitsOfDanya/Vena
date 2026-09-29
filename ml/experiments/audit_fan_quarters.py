import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    args = parser.parse_args()
    cache, _, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years=0)
    y = valid["target"].to_numpy()
    blend = (linear + tree) / 2
    quarters = valid["ts"].dt.quarter.to_numpy()
    for quarter in np.unique(quarters):
        selected = quarters == quarter
        if y[selected].sum() == 0:
            continue
        baseline_ap = average_precision_score(y[selected], linear[selected])
        blend_ap = average_precision_score(y[selected], blend[selected])
        emit({
            "year": args.valid_year, "quarter": int(quarter),
            "n_candidates": int(selected.sum()),
            "n_positive": int(y[selected].sum()),
            "baseline_ap": float(baseline_ap),
            "blend_ap": float(blend_ap),
            "ap_gain": float(blend_ap - baseline_ap),
        })


if __name__ == "__main__":
    main()
