import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, evaluate, experiments, recipes, training
from pipeline.formal import metrics as fm

HORIZON = 24
EMBARGO = pd.Timedelta(hours=168)
CHRONIC_QUANTILE = 0.67
OUTPUT = os.path.join(os.path.dirname(__file__), "smoke_routing_2026h1.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5, 10))
    return {"avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "top5_per_day": top["precision_top5_per_day"], "top10_per_day": top["precision_top10_per_day"]}


def chronic_channels(episodes, before):
    counts = episodes.loc[episodes["episode_start"] < before].groupby("channel_id", observed=True).size()
    return set(counts[counts >= counts.quantile(CHRONIC_QUANTILE)].index.astype(str))


def fit_segments(frame, rows, chronic, columns):
    segment = frame["channel_id"].astype(str).isin(chronic).values
    models = {}
    for name, mask in (("chronic", rows & segment), ("other", rows & ~segment)):
        models[name] = recipes.fit("catboost", frame.loc[mask, columns], frame.loc[mask, "target"])
        log(f"{name}: {int(mask.sum())} rows")
    return models


def score_segments(frame, rows, chronic, models, columns, calibrators=None):
    segment = frame["channel_id"].astype(str).isin(chronic).values
    raw = np.zeros(len(frame))
    for name, mask in (("chronic", rows & segment), ("other", rows & ~segment)):
        if mask.any():
            score = models[name].predict_proba(frame.loc[mask, columns])
            raw[mask] = calibration.apply_isotonic(calibrators[name], score) if calibrators else score
    return raw[rows], segment[rows]


def main() -> None:
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES["smoke"])
    frame = ctx.build(horizon_hours=HORIZON).reset_index(drop=True)
    columns = training.feature_columns()
    year = frame["ts"].dt.year
    select = (year == 2025).values
    recent = ((year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=HORIZON))).values
    target = frame["target"].values

    before_2025 = (frame["ts"] < pd.Timestamp("2025-01-01") - EMBARGO).values
    chronic_2025 = chronic_channels(ctx.episodes, pd.Timestamp("2025-01-01"))
    staging = fit_segments(frame, before_2025, chronic_2025, columns)
    raw_2025, segment_2025 = score_segments(frame, select, chronic_2025, staging, columns)
    calibrators = {name: calibration.fit_isotonic(raw_2025[mask], target[select][mask])
                   for name, mask in (("chronic", segment_2025), ("other", ~segment_2025))}
    single_2024 = recipes.fit("catboost", frame.loc[before_2025, columns], target[before_2025])
    routed_2025 = np.zeros(int(select.sum()))
    for name, mask in (("chronic", segment_2025), ("other", ~segment_2025)):
        routed_2025[mask] = calibration.apply_isotonic(calibrators[name], raw_2025[mask])
    y25, ts25 = target[select], frame.loc[select, "ts"].values

    through_2025 = (frame["ts"] < pd.Timestamp("2026-01-01") - EMBARGO).values
    chronic_2026 = chronic_channels(ctx.episodes, pd.Timestamp("2026-01-01"))
    final = fit_segments(frame, through_2025, chronic_2026, columns)
    routed, segment = score_segments(frame, recent, chronic_2026, final, columns, calibrators)
    single = recipes.fit("catboost", frame.loc[through_2025, columns], target[through_2025])
    production = artifacts.load_artifact("smoke_24h")[0]
    y, ts = target[recent], frame.loc[recent, "ts"].values
    report = {
        "chronic_share_of_candidates_2026h1": round(float(segment.mean()), 4),
        "base_rate_chronic_2026h1": round(float(y[segment].mean()), 4),
        "base_rate_other_2026h1": round(float(y[~segment].mean()), 4),
        "stage1_2025": {"single_catboost": summary(y25, single_2024.predict_proba(frame.loc[select, columns]), ts25),
                        "routed": summary(y25, routed_2025, ts25)},
        "stage2_2026h1": {"single_catboost": summary(y, single.predict_proba(frame.loc[recent, columns]), ts),
                          "routed": summary(y, routed, ts),
                          "production_smoke_24h": summary(y, production.predict_proba(frame.loc[recent, columns]), ts)},
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    log(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
