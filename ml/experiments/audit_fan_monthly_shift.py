import argparse

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    args = parser.parse_args()
    cache, _, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years=0)
    scored = valid.reset_index(drop=True).copy()
    scored["linear_score"] = linear
    scored["blend_score"] = (linear + tree) / 2
    scored["month_group"] = scored["ts"].dt.to_period("M")
    for month, group in scored.groupby("month_group", sort=True):
        labels = group["target"].to_numpy()
        linear_score = group["linear_score"].to_numpy()
        blend_score = group["blend_score"].to_numpy()
        concentration = group["channel_id"].value_counts(normalize=True)
        top10_ids = group["channel_id"].value_counts().head(10).index
        top10 = group["channel_id"].isin(top10_ids)
        linear_ap = float(average_precision_score(labels, linear_score))
        blend_ap = float(average_precision_score(labels, blend_score))
        transitions = group["trigger"] == "transition"
        emit({
            "sensor": "fan", "month": str(month),
            "n_candidates": len(group), "n_positive": int(labels.sum()),
            "positive_rate": float(labels.mean()),
            "n_channels": int(group["channel_id"].nunique()),
            "top10_channel_candidate_share": float(concentration.head(10).sum()),
            "top10_channel_n_candidates": int(top10.sum()),
            "top10_channel_n_positive": int(group.loc[top10, "target"].sum()),
            "top10_channel_transition_share": float((group.loc[top10, "trigger"] == "transition").mean()),
            "transition_candidate_share": float(transitions.mean()),
            "transition_positive_rate": (
                float(group.loc[transitions, "target"].mean()) if transitions.any() else None
            ),
            "median_events_7d": float(group["events_7d"].median()),
            "median_ewma_event_rate_7d": float(group["ewma_event_rate_7d"].median()),
            "median_linear_score": float(np.median(linear_score)),
            "median_blend_score": float(np.median(blend_score)),
            "linear_ap": linear_ap, "blend_ap": blend_ap,
            "ap_gain": blend_ap - linear_ap,
        })
    largest_month = scored["month_group"].value_counts().idxmax()
    rest = scored.loc[scored["month_group"] != largest_month]
    rest_labels = rest["target"].to_numpy()
    rest_linear_ap = float(average_precision_score(rest_labels, rest["linear_score"]))
    rest_blend_ap = float(average_precision_score(rest_labels, rest["blend_score"]))
    emit({
        "sensor": "fan", "valid_year": args.valid_year,
        "scope": "excluding_largest_candidate_month",
        "excluded_month": str(largest_month),
        "n_candidates": len(rest), "n_positive": int(rest_labels.sum()),
        "linear_ap": rest_linear_ap, "blend_ap": rest_blend_ap,
        "ap_gain": rest_blend_ap - rest_linear_ap,
    })
    largest = scored.loc[scored["month_group"] == largest_month]
    top10_ids = largest["channel_id"].value_counts().head(10).index
    without_top10 = ~scored["channel_id"].isin(top10_ids)
    for scope, subset in (
        ("excluding_top10_channels_of_largest_month", scored.loc[without_top10]),
        ("largest_month_excluding_its_top10_channels", scored.loc[
            (scored["month_group"] == largest_month) & without_top10
        ]),
    ):
        subset_labels = subset["target"].to_numpy()
        subset_linear_ap = float(average_precision_score(subset_labels, subset["linear_score"]))
        subset_blend_ap = float(average_precision_score(subset_labels, subset["blend_score"]))
        emit({
            "sensor": "fan", "valid_year": args.valid_year,
            "scope": scope, "selected_month": str(largest_month),
            "n_candidates": len(subset), "n_positive": int(subset_labels.sum()),
            "linear_ap": subset_linear_ap, "blend_ap": subset_blend_ap,
            "ap_gain": subset_blend_ap - subset_linear_ap,
        })


if __name__ == "__main__":
    main()
