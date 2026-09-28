"""Audit chronological threshold alerts with a fixed cooldown."""

import argparse

import numpy as np
import pandas as pd

from experiments.common import emit, threshold_at_precision
from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline import alerts


def summarize_threshold(frame, episodes, threshold, cooldown_hours=24):
    """Evaluate alerts in timestamp order without using future observations."""
    raw = frame.loc[frame["score"] >= threshold]
    selected = alerts.select_alerts_by_threshold(frame, "score", threshold, cooldown_hours)
    period_start = frame["ts"].min()
    period_end = frame["ts"].max()
    period_episodes = episodes.loc[
        (episodes["episode_start"] >= period_start)
        & (episodes["episode_start"] <= period_end)
    ]
    detected, lead = alerts.episode_level_recall(selected, period_episodes, 72)
    n_days = (period_end - period_start).total_seconds() / 86400
    return {
        "threshold": float(threshold),
        "n_raw": len(raw),
        "n_alerts": len(selected),
        "alerts_per_day": float(len(selected) / n_days),
        "alert_precision": float(selected["target"].mean()) if len(selected) else None,
        "episode_recall": float(detected.mean()) if len(detected) else None,
        "n_episodes": len(period_episodes),
        "median_lead_hours": float(np.nanmedian(lead)) if detected.any() else None,
    }


def main():
    """Report a development grid or transfer thresholds from a prior year."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("pump", "fan"), default="pump")
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--window-years", type=int, default=None)
    parser.add_argument("--model", choices=("linear", "blend"), default="blend")
    parser.add_argument("--thresholds", help="Comma-separated fixed thresholds from prior year")
    parser.add_argument("--cooldowns", default="24", help="Comma-separated cooldown hours")
    args = parser.parse_args()
    window_years = args.window_years
    if window_years is None:
        window_years = 3 if args.sensor == "pump" else 0
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    full = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    valid, (linear, tree), seconds = fit_scores(full, args.valid_year, window_years)
    frame = valid[["channel_id", "ts", "target"]].copy()
    frame["score"] = linear if args.model == "linear" else (linear + tree) / 2
    if args.thresholds:
        thresholds = [float(value) for value in args.thresholds.split(",")]
    else:
        quantiles = [0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995, 0.997, 0.999]
        thresholds = list(np.quantile(frame["score"], quantiles))
        p70_threshold = threshold_at_precision(frame["target"], frame["score"])
        if p70_threshold is not None:
            thresholds.append(p70_threshold)
    for cooldown in map(int, args.cooldowns.split(",")):
        for threshold in thresholds:
            result = summarize_threshold(frame, episodes, threshold, cooldown)
            result.update({
                "sensor": args.sensor, "model": args.model,
                "window_years": window_years,
                "valid_year": args.valid_year, "cooldown_hours": cooldown,
                "fit_score_seconds": seconds,
            })
            emit(result)


if __name__ == "__main__":
    main()
