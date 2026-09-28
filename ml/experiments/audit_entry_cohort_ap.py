"""Compare ranking by first observed channel year without exporting IDs."""

import argparse

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths

EVENT_CACHES = {
    "fan": "analysis/ml_ready/cache/events_Состояние_вентилятора.parquet",
    "pump": "analysis/ml_ready/cache/events_Состояние_насоса.parquet",
}


def subgroup_ap(labels, scores):
    """Only define AP when both classes occur in the subgroup."""
    if labels.sum() in (0, len(labels)):
        return None
    return float(average_precision_score(labels, scores))


def main():
    """Use raw first-seen time only to audit the fixed validation scores."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=tuple(EVENT_CACHES), required=True)
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), default=2025)
    args = parser.parse_args()
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    window_years = 3 if args.sensor == "pump" else 0
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, window_years)
    first_seen = (
        pd.read_parquet(EVENT_CACHES[args.sensor], columns=["channel_id", "ts"])
        .groupby("channel_id", observed=True)["ts"]
        .min()
    )
    new_ids = first_seen.loc[first_seen >= pd.Timestamp(f"{args.valid_year}-01-01")].index
    is_new = valid["channel_id"].isin(new_ids).to_numpy()
    labels = valid["target"].to_numpy()
    blend = (linear + tree) / 2
    for name, mask in (
        ("all", pd.Series(True, index=valid.index).to_numpy()),
        ("new", is_new),
        ("established", ~is_new),
    ):
        local = labels[mask]
        linear_ap = subgroup_ap(local, linear[mask])
        blend_ap = subgroup_ap(local, blend[mask])
        emit({
            "sensor": args.sensor,
            "valid_year": args.valid_year,
            "cohort": name,
            "n_channels": int(valid.loc[mask, "channel_id"].nunique()),
            "n_candidates": len(local),
            "n_positive": int(local.sum()),
            "positive_rate": float(local.mean()) if len(local) else None,
            "linear_ap": linear_ap,
            "blend_ap": blend_ap,
            "ap_gain": blend_ap - linear_ap if blend_ap is not None else None,
        })


if __name__ == "__main__":
    main()
