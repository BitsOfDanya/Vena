import argparse
import json

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline.formal.metrics import eval_at_threshold


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("pump", "fan"), required=True)
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    parser.add_argument("--frozen-from", required=True)
    args = parser.parse_args()
    with open(args.frozen_from, encoding="utf-8") as source:
        prior = next(row for row in map(json.loads, source) if row["linear_weight"] == 0.5)
    threshold = prior["threshold_p70"]
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    window = 3 if args.sensor == "pump" else 0
    valid_frame, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years=window)
    score = (linear + tree) / 2
    labels = valid_frame["target"].to_numpy()
    cutoff = pd.Timestamp(f"{args.valid_year}-01-01") + pd.Timedelta(hours=72)
    safe = (valid_frame["ts"] >= cutoff).to_numpy()
    result = {
        "sensor": args.sensor, "valid_year": args.valid_year,
        "prior_year": prior["valid_year"], "threshold": threshold,
        "excluded_first_72h": int((~safe).sum()),
        "excluded_positive": int(labels[~safe].sum()),
        "full": {
            "n": len(labels), "n_positive": int(labels.sum()),
            "ap": float(average_precision_score(labels, score)),
            "at_frozen_p70": eval_at_threshold(labels, score, threshold),
        },
        "boundary_disjoint": {
            "n": int(safe.sum()), "n_positive": int(labels[safe].sum()),
            "ap": float(average_precision_score(labels[safe], score[safe])),
            "at_frozen_p70": eval_at_threshold(labels[safe], score[safe], threshold),
        },
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
