import argparse
import json

import numpy as np
import pandas as pd

from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline import alerts


def channel_counts(frame, episodes, score, threshold):
    scored = frame[["channel_id", "ts", "target"]].copy()
    scored["score"] = score
    selected = alerts.select_alerts_by_threshold(scored, "score", threshold, 24)
    detected, _ = alerts.episode_level_recall(selected, episodes, 72)
    channel_index = pd.Index(pd.unique(pd.concat([frame["channel_id"], episodes["channel_id"]])))
    alert_count = selected.groupby("channel_id", observed=True).size().reindex(channel_index, fill_value=0)
    alert_true = selected.groupby("channel_id", observed=True)["target"].sum().reindex(channel_index, fill_value=0)
    episode_count = episodes.groupby("channel_id", observed=True).size().reindex(channel_index, fill_value=0)
    episode_detected = (
        episodes.assign(detected=detected)
        .groupby("channel_id", observed=True)["detected"].sum()
        .reindex(channel_index, fill_value=0)
    )
    return np.column_stack((alert_count, alert_true, episode_count, episode_detected))


def rates(counts):
    summed = counts.sum(axis=0)
    return np.array([
        summed[1] / summed[0] if summed[0] else np.nan,
        summed[3] / summed[2] if summed[2] else np.nan,
    ])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    parser.add_argument("--linear-threshold", type=float, required=True)
    parser.add_argument("--blend-threshold", type=float, required=True)
    parser.add_argument("--replicates", type=int, default=1000)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("fan", False)
    full = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    valid, (linear, tree), _ = fit_scores(full, args.valid_year, 0)
    period_episodes = episodes.loc[
        (episodes["episode_start"] >= valid["ts"].min())
        & (episodes["episode_start"] <= valid["ts"].max())
    ]
    baseline = channel_counts(valid, period_episodes, linear, args.linear_threshold)
    blend = channel_counts(valid, period_episodes, (linear + tree) / 2, args.blend_threshold)
    observed = rates(blend) - rates(baseline)
    rng = np.random.default_rng(20260924)
    differences = np.empty((args.replicates, 2))
    for repeat in range(args.replicates):
        sample = rng.integers(0, len(baseline), len(baseline))
        differences[repeat] = rates(blend[sample]) - rates(baseline[sample])
    result = {
        "valid_year": args.valid_year,
        "linear_threshold": args.linear_threshold,
        "blend_threshold": args.blend_threshold,
        "n_channels": len(baseline),
        "replicates": args.replicates,
        "baseline": rates(baseline).tolist(),
        "blend": rates(blend).tolist(),
        "gain": observed.tolist(),
        "gain_ci95": np.quantile(differences, [0.025, 0.975], axis=0).T.tolist(),
        "fraction_positive_gain": (differences > 0).mean(axis=0).tolist(),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
