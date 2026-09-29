import argparse

import pandas as pd

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline import alerts


def summarize_months(frame, episodes, score, threshold, model):
    scored = frame[["channel_id", "ts", "target"]].copy()
    scored["score"] = score
    selected = alerts.select_alerts_by_threshold(scored, "score", threshold, 24)
    detected, _ = alerts.episode_level_recall(selected, episodes, 72)
    selected = selected.assign(month=selected["ts"].dt.to_period("M"))
    episode_results = episodes.assign(
        month=episodes["episode_start"].dt.to_period("M"),
        detected=detected,
    )
    periods = frame["ts"].dt.to_period("M")
    for month in sorted(periods.unique()):
        month_alerts = selected.loc[selected["month"] == month]
        month_episodes = episode_results.loc[episode_results["month"] == month]
        n_days = frame.loc[periods == month, "ts"].dt.date.nunique()
        emit({
            "model": model, "month": str(month),
            "threshold": threshold,
            "n_alerts": len(month_alerts),
            "alert_precision": (
                float(month_alerts["target"].mean()) if len(month_alerts) else None
            ),
            "alerts_per_day": float(len(month_alerts) / n_days),
            "n_episodes": len(month_episodes),
            "n_detected_episodes": int(month_episodes["detected"].sum()),
            "episode_recall": (
                float(month_episodes["detected"].mean()) if len(month_episodes) else None
            ),
        })


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    parser.add_argument("--linear-threshold", type=float, required=True)
    parser.add_argument("--blend-threshold", type=float, required=True)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, 0)
    period_episodes = episodes.loc[
        (episodes["episode_start"] >= valid["ts"].min())
        & (episodes["episode_start"] <= valid["ts"].max())
    ]
    summarize_months(valid, period_episodes, linear, args.linear_threshold, "linear")
    summarize_months(
        valid, period_episodes, (linear + tree) / 2, args.blend_threshold, "blend",
    )


if __name__ == "__main__":
    main()
