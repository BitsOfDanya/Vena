import argparse
import json

import numpy as np
import pandas as pd

from experiments.run_blend_experiment import fit_scores
from experiments.run_recency_experiment import cache_paths
from pipeline import alerts


def prior_score_thresholds(timestamps, scores, initial_threshold, lookback_days, quantile=0.95):
    dates = np.asarray(timestamps).astype("datetime64[D]")
    thresholds = np.full(len(scores), initial_threshold, dtype=float)
    for day in np.unique(dates):
        past_end = np.searchsorted(dates, day, side="left")
        past_start = np.searchsorted(dates, day - np.timedelta64(lookback_days, "D"), side="left")
        if past_end - past_start >= 500:
            thresholds[dates == day] = np.quantile(scores[past_start:past_end], quantile)
    return thresholds


def summarize(frame, episodes, scores, thresholds):
    scored = frame[["channel_id", "ts", "target"]].copy()
    scored["excess"] = scores - thresholds
    selected = alerts.select_alerts_by_threshold(scored, "excess", 0, 24)
    detected, _ = alerts.episode_level_recall(selected, episodes, 72)
    days = (frame["ts"].max() - frame["ts"].min()).total_seconds() / 86400
    return {
        "n_alerts": len(selected),
        "alerts_per_day": float(len(selected) / days),
        "alert_precision": float(selected["target"].mean()) if len(selected) else None,
        "episode_recall": float(detected.mean()) if len(detected) else None,
        "median_threshold": float(np.median(thresholds)),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    parser.add_argument("--linear-initial", type=float, required=True)
    parser.add_argument("--blend-initial", type=float, required=True)
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    valid, (linear, tree), _ = fit_scores(frame, args.valid_year, 0)
    order = np.argsort(valid["ts"].to_numpy(), kind="stable")
    valid = valid.iloc[order].reset_index(drop=True)
    starts = episodes.loc[
        (episodes["episode_start"] >= valid["ts"].min())
        & (episodes["episode_start"] <= valid["ts"].max())
    ]
    for name, score, initial in (
        ("linear", linear[order], args.linear_initial),
        ("blend", ((linear + tree) / 2)[order], args.blend_initial),
    ):
        for lookback in (0, 30, 90):
            thresholds = (
                np.full(len(score), initial)
                if lookback == 0 else prior_score_thresholds(
                    valid["ts"].to_numpy(), score, initial, lookback,
                )
            )
            result = summarize(valid, starts, score, thresholds)
            result.update({
                "valid_year": args.valid_year,
                "model": name,
                "lookback_days": lookback,
                "initial_threshold": initial,
                "n_episodes": len(starts),
            })
            print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
