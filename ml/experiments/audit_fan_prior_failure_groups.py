import argparse

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths


def subgroup_ap(labels, scores):
    if labels.sum() in (0, len(labels)):
        return None
    return float(average_precision_score(labels, scores))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, 0)
    cutoff = pd.Timestamp(f"{args.valid_year}-01-01") - pd.Timedelta(hours=168)
    prior_channels = set(episodes.loc[episodes["episode_start"] < cutoff, "channel_id"])
    known = valid["channel_id"].isin(prior_channels).to_numpy()
    labels = valid["target"].to_numpy()
    blend = (linear + tree) / 2
    valid_episodes = episodes.loc[
        (episodes["episode_start"] >= valid["ts"].min())
        & (episodes["episode_start"] <= valid["ts"].max())
    ]
    for name, mask in (("prior_failure", known), ("no_prior_failure", ~known)):
        local_labels = labels[mask]
        local_frame = valid.loc[mask]
        local_episodes = valid_episodes["channel_id"].isin(prior_channels)
        n_episodes = int(local_episodes.sum()) if name == "prior_failure" else int((~local_episodes).sum())
        emit({
            "sensor": "fan", "valid_year": args.valid_year,
            "group": name, "n_channels": int(local_frame["channel_id"].nunique()),
            "n_candidates": len(local_labels),
            "n_positive": int(local_labels.sum()),
            "n_failure_episodes": n_episodes,
            "positive_rate": float(local_labels.mean()),
            "linear_ap": subgroup_ap(local_labels, linear[mask]),
            "blend_ap": subgroup_ap(local_labels, blend[mask]),
        })


if __name__ == "__main__":
    main()
