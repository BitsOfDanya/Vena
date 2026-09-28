"""Compare fixed probability and log-odds fusion of pump models."""

import argparse
import json
import time

import numpy as np
import pandas as pd
from scipy.special import expit, logit
from sklearn.metrics import average_precision_score

from experiments.common import emit, operational_summary, threshold_at_precision
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics


def fused_scores(linear, tree):
    """Return a small prespecified set of calibration-free fusions."""
    safe_linear = np.clip(linear, 1e-6, 1 - 1e-6)
    safe_tree = np.clip(tree, 1e-6, 1 - 1e-6)
    linear_logit = logit(safe_linear)
    tree_logit = logit(safe_tree)
    return {
        "arithmetic_50": 0.5 * linear + 0.5 * tree,
        "logit_50": expit(0.5 * linear_logit + 0.5 * tree_logit),
        "logit_25": expit(0.25 * linear_logit + 0.75 * tree_logit),
        "logit_75": expit(0.75 * linear_logit + 0.25 * tree_logit),
        "geometric_probability": np.sqrt(safe_linear * safe_tree),
    }


def main():
    """Evaluate fixed score transforms on a chronological holdout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--variants", default="arithmetic_50,logit_50,logit_25,logit_75,geometric_probability")
    parser.add_argument("--frozen-from")
    args = parser.parse_args()
    frozen = {}
    if args.frozen_from:
        with open(args.frozen_from, encoding="utf-8") as source:
            frozen = {row["variant"]: row for row in map(json.loads, source)}
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    tick = time.monotonic()
    valid_frame, (linear, tree), fit_seconds = fit_scores(frame, args.valid_year)
    y = valid_frame["target"].to_numpy()
    h1 = valid_frame["ts"].dt.month.to_numpy() <= 6
    for name, score in fused_scores(linear, tree).items():
        if name not in args.variants.split(","):
            continue
        metrics = frontier_metrics(y, score)
        metrics.update({
            "variant": name, "valid_year": args.valid_year,
            "n_valid": len(y), "n_positive": int(y.sum()),
            "half_ap": {
                "h1": float(average_precision_score(y[h1], score[h1])) if h1.any() else None,
                "h2": float(average_precision_score(y[~h1], score[~h1])) if (~h1).any() else None,
            },
            "threshold_p70": threshold_at_precision(y, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "fit_score_seconds": fit_seconds,
            "elapsed_seconds": round(time.monotonic() - tick, 1),
        })
        if name in frozen and frozen[name]["threshold_p70"] is not None:
            metrics["frozen_from_year"] = frozen[name]["valid_year"]
            metrics["at_frozen_p70"] = eval_at_threshold(y, score, frozen[name]["threshold_p70"])
        emit(metrics)


if __name__ == "__main__":
    main()
