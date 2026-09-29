import json

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import fit_and_score
from pipeline.formal.metrics import eval_at_threshold


def saved_threshold(path, key, value):
    with open(path, encoding="utf-8") as source:
        for row in map(json.loads, source):
            if row[key] == value:
                return row["threshold_p70"]
    raise ValueError(f"missing threshold for {value}")


def main():
    frame = pd.read_parquet("analysis/ml_ready/pump72_features.parquet")
    _, baseline = fit_and_score(frame, 2026, "baseline", 168)
    valid_frame, (linear, tree), _ = fit_scores(frame, 2026)
    blend = 0.5 * linear + 0.5 * tree
    baseline_threshold = saved_threshold(
        "experiments/pump_lr_validation_2025.jsonl", "variant", "baseline",
    )
    blend_threshold = saved_threshold(
        "experiments/pump_blend_validation_2025.jsonl", "linear_weight", 0.5,
    )
    labels = valid_frame["target"].to_numpy()
    quarters = valid_frame["ts"].dt.quarter
    for quarter in sorted(quarters.unique()):
        mask = (quarters == quarter).to_numpy()
        emit({
            "year": 2026, "quarter": int(quarter),
            "n_candidates": int(mask.sum()), "n_positive": int(labels[mask].sum()),
            "baseline_ap": average_precision_score(labels[mask], baseline[mask]),
            "blend_ap": average_precision_score(labels[mask], blend[mask]),
            "baseline_frozen": eval_at_threshold(
                labels[mask], baseline[mask], baseline_threshold,
            ),
            "blend_frozen": eval_at_threshold(
                labels[mask], blend[mask], blend_threshold,
            ),
        })


if __name__ == "__main__":
    main()
