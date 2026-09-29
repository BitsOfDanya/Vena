import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit, operational_summary
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths, fit_and_score
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics

EVENT_CACHE = "analysis/ml_ready/cache/events_Состояние_насоса.parquet"
FROZEN_THRESHOLD_2024 = 0.7572332851137136


def subgroup_ap(labels, scores, mask):
    selected = labels[mask]
    if len(selected) == 0 or selected.sum() in (0, len(selected)):
        return None
    return float(average_precision_score(selected, scores[mask]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    events = pd.read_parquet(EVENT_CACHE, columns=["channel_id", "ts"])
    first = events.groupby("channel_id", observed=True)["ts"].min()
    _, baseline = fit_and_score(frame, args.valid_year, "baseline", 168)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year)
    blend = (linear + tree) / 2
    age = (valid["ts"] - valid["channel_id"].map(first)).dt.total_seconds().to_numpy() / 86400
    short = age < 30
    fallback = np.where(short, baseline, blend)
    labels = valid["target"].to_numpy()
    for name, score in (("baseline", baseline), ("blend", blend), ("fallback_30d", fallback)):
        metrics = frontier_metrics(labels, score)
        metrics.update({
            "variant": name, "valid_year": args.valid_year,
            "n_valid": len(labels), "n_positive": int(labels.sum()),
            "n_short": int(short.sum()), "n_positive_short": int(labels[short].sum()),
            "ap_short": subgroup_ap(labels, score, short),
            "ap_older": subgroup_ap(labels, score, ~short),
            "at_frozen_2024": eval_at_threshold(labels, score, FROZEN_THRESHOLD_2024),
            "short_at_frozen_2024": (
                eval_at_threshold(labels[short], score[short], FROZEN_THRESHOLD_2024)
                if short.any() else None
            ),
            "operational": operational_summary(valid, score, episodes),
        })
        emit(metrics)


if __name__ == "__main__":
    main()
