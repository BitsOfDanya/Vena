"""Operational report of the production models: drift, recalibration, lead time, daily top-K.

For every forecasting model on its held-out periods:
- drift: base rate of the target and population stability of the raw score
  between the validation year and the first half of 2026;
- recalibration: the calibrator is refitted on the two most recent full years
  (2024 and 2025), which smooths year-to-year swings of the event rate, and
  both the old (2024) and the new calibrator are measured on 2026H1;
- lead time: at the model's "high" and "medium" bands, how many episodes were
  warned, how precise the alerts were and how many hours ahead they came;
- daily top-K: precision of the K highest-risk channels per day, the rule for
  planning inspections of pumps and fans.
Results go to results/model_report.json; the pooled calibrators replace the 2024 ones.
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, evaluate, experiments, extract, weather as weather_mod
from pipeline.targets import evaluation, flood

OUTPUT = os.path.join(config.ROOT, "results", "model_report.json")
DEVICE_MODELS = {"pump": ["pump_24h", "pump_72h", "pump_baseline_72h"], "fan": ["fan_24h", "fan_72h"], "smoke": ["smoke_24h"]}
TOP_COUNTS = (5, 10, 20)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def psi(expected, actual, bins=10):
    """Population stability index of a score between two periods."""
    edges = np.unique(np.quantile(expected, np.linspace(0, 1, bins + 1)))
    edges[0], edges[-1] = -np.inf, np.inf
    left = np.histogram(expected, edges)[0] / len(expected)
    right = np.histogram(actual, edges)[0] / len(actual)
    left, right = np.clip(left, 1e-6, None), np.clip(right, 1e-6, None)
    return float(np.sum((right - left) * np.log(right / left)))


def ece(target, probability):
    return round(float(calibration.expected_calibration_error(target, probability)[0]), 4)


def study(name, frame, episodes, horizon, recent_mask, fit_mask, reference_mask):
    model, meta = artifacts.load_artifact(name)
    columns = meta["feature_columns"]
    old = artifacts.load_calibrator(name)
    raw = model.predict_proba(frame[columns])
    target = frame["target"].values

    pooled = fit_mask | reference_mask
    new = calibration.fit_isotonic(raw[pooled], target[pooled])
    # A model trained through 2025 has seen the calibration years; keep its own calibrator.
    in_sample = int(meta["training_period"]["train_years"].split("-")[-1]) >= 2024
    if in_sample:
        new = old
    recent_raw, recent_target = raw[recent_mask], target[recent_mask]
    report = {
        "drift": {
            "base_rate_reference": round(float(target[reference_mask].mean()), 4),
            "base_rate_2025": round(float(target[fit_mask].mean()), 4),
            "base_rate_2026h1": round(float(recent_target.mean()), 4),
            "score_psi_reference_vs_2026h1": round(psi(raw[reference_mask], recent_raw), 4),
        },
        "calibration_2026h1": {
            "predicted_old": round(float(np.mean(calibration.apply_isotonic(old, recent_raw))), 4) if old is not None else None,
            "predicted_new": round(float(np.mean(calibration.apply_isotonic(new, recent_raw))), 4),
            "observed": round(float(recent_target.mean()), 4),
            "ece_old": ece(recent_target, np.clip(calibration.apply_isotonic(old, recent_raw), 0, 1)) if old is not None else None,
            "ece_new": ece(recent_target, np.clip(calibration.apply_isotonic(new, recent_raw), 0, 1)),
        },
    }

    scored = frame.loc[recent_mask, ["channel_id", "ts"]].assign(target=recent_target, score=recent_raw)
    bands = meta["model_config"].get("risk_level_thresholds", {})
    report["lead_time_2026h1"] = {}
    for level in ("high", "medium"):
        if level not in bands:
            continue
        point = evaluation.operating_point_report(scored, bands[level], episodes, horizon)
        report["lead_time_2026h1"][level] = {
            key: (round(float(point[key]), 4) if point[key] is not None else None)
            for key in ("episode_recall", "alert_precision_dedup", "median_lead_time_hours", "alerts_per_day")
        }
    top = evaluate.evaluate_daily_topk_fixed(scored["ts"].values, recent_target, recent_raw, counts=TOP_COUNTS)
    report["daily_top_k_2026h1"] = {str(k): top.get(f"precision_top{k}_per_day") for k in TOP_COUNTS}

    if in_sample:
        log(f"{name}: trained through 2025, calibrator kept")
        return report
    joblib.dump(new, os.path.join(artifacts.artifact_dir(name), "calibrator.joblib"))
    meta_path = os.path.join(artifacts.artifact_dir(name), "meta.json")
    with open(meta_path, encoding="utf-8") as handle:
        stored = json.load(handle)
    stored["model_config"]["calibration"] = {
        **stored["model_config"].get("calibration", {}),
        "method": "isotonic",
        "fit_period": "2024-2025",
        "evaluated_on": "2026H1",
        "ece_2024_fit": report["calibration_2026h1"]["ece_old"],
        "ece_calibrated": report["calibration_2026h1"]["ece_new"],
    }
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, indent=2, ensure_ascii=False)
    log(f"{name}: {json.dumps(report['calibration_2026h1'])}")
    return report


def periods(frame, horizon):
    year = frame["ts"].dt.year
    complete = frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon)
    return (year == 2026) & complete, year == 2025, year == 2024


def main() -> None:
    report = {}
    for device, names in DEVICE_MODELS.items():
        ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        for name in names:
            horizon = artifacts.load_artifact(name)[1]["model_config"]["horizon_hours"]
            frame = ctx.build(horizon_hours=horizon).reset_index(drop=True)
            recent, fit, reference = (mask.values for mask in periods(frame, horizon))
            report[name] = study(name, frame, ctx.episodes, horizon, recent, fit, reference)

    events = extract.extract_events(config.SENSOR_ALIASES["pump"])
    frame, episodes, _ = flood.build_frame(events, weather_mod.fetch_weather(), 24)
    frame = frame.reset_index(drop=True)
    recent, fit, reference = (mask.values for mask in periods(frame, 24))
    report["flood_24h"] = study("flood_24h", frame, episodes, 24, recent, fit, reference)

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(f"report -> {OUTPUT}")


if __name__ == "__main__":
    main()
