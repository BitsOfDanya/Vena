"""Refit study: a newer training window and other model families.

The frozen models are trained through 2023 (phase through 2024), and the event
rates of several devices changed since then (results/model_report.json). For
each model the study:
1. fits every recipe (model family x training window) on data before 2025 and
   measures average precision on 2025;
2. refits two candidates on data through 2025: the recipe that was best on 2025
   and the recipe of the current artifact. Each refit is calibrated by the
   isotonic map of its pre-2025 counterpart on 2025, a year that counterpart has not seen;
3. compares the refits with the current artifact on the first half of 2026, which
   none of them has seen, and with --promote replaces the artifact by the better
   refit when it gains more than MIN_GAIN of average precision.
The best recipe on 2025 is not always the best on 2026H1 (linear models lose
most under the fan drift), hence the second candidate. Risk bands of a promoted
model keep the alert volume of the current one on 2026H1.
Results go to results/refit_study.json.
"""

import argparse
import json
import os
import time

import joblib
import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, evaluate, experiments, extract, recipes, weather as weather_mod
from pipeline.formal import metrics as fm
from pipeline.targets import flood, modules

EMBARGO = pd.Timedelta(hours=168)
SELECTION_YEAR = 2025
RECENT_YEAR = 2026
WINDOWS = {"all": None, "3y": 3}
MIN_GAIN = 0.005
DEVICE_MODELS = {"pump_24h": ("pump", 24), "pump_72h": ("pump", 72), "fan_24h": ("fan", 24),
                 "fan_72h": ("fan", 72), "smoke_24h": ("smoke", 24)}
OUTPUT = os.path.join(config.ROOT, "results", "refit_study.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def frames(names):
    """Candidate frame and horizon of every studied model."""
    ctx = None
    for name, (device, horizon) in DEVICE_MODELS.items():
        if name not in names:
            continue
        if ctx is None or ctx.sensor_type != config.SENSOR_ALIASES[device]:
            ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        yield name, ctx.build(horizon_hours=horizon), horizon
    ctx = None
    if "flood_24h" in names:
        events = extract.extract_events(config.SENSOR_ALIASES["pump"])
        yield "flood_24h", flood.build_frame(events, weather_mod.fetch_weather(), 24)[0], 24
    if "phase_24h" in names:
        events = extract.extract_events(modules.PHASE_SENSOR)
        frame = modules.build_phase_frame(events, horizons=(24,), include_lockbox=True)[0]
        yield "phase_24h", frame.rename(columns={"any_y24": "target"}), 24


def current_window(meta):
    start = int(meta["training_period"]["train_years"].split("-")[0])
    return "all" if start <= config.TRAIN_YEARS[0] else "3y"


def training_rows(frame, before_year, window):
    rows = frame["ts"] < pd.Timestamp(f"{before_year}-01-01") - EMBARGO
    if WINDOWS[window]:
        rows &= frame["ts"].dt.year >= before_year - WINDOWS[window]
    return rows


def quality(target, raw, probability, ts):
    frontier = fm.frontier_metrics(target, raw)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, raw, counts=(5,))
    return {
        "avg_precision": round(float(frontier["pr_auc"]), 4),
        "roc_auc": round(float(frontier["roc_auc"]), 4),
        "recall_at_precision_0.7": round(float(frontier["recall_at_precision_0.7"]), 4),
        "precision_at_recall_0.5": round(float(frontier["precision_at_recall_0.5"]), 4),
        "precision_top5_per_day": top["precision_top5_per_day"],
        "ece": round(float(calibration.expected_calibration_error(target, probability)[0]), 4) if probability is not None else None,
    }


def study(name, frame, horizon, promote):
    current, meta = artifacts.load_artifact(name)
    columns = meta["feature_columns"]
    frame = frame.reset_index(drop=True)
    year = frame["ts"].dt.year
    select = (year == SELECTION_YEAR).values
    recent = ((year == RECENT_YEAR) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon))).values
    target = frame["target"].values
    log(f"{name}: {len(frame)} candidates, selection {int(select.sum())}, recent {int(recent.sum())}")

    candidates, fitted = [], {}
    for window in WINDOWS:
        rows = training_rows(frame, SELECTION_YEAR, window).values
        for recipe in recipes.RECIPES:
            started = time.time()
            model = recipes.fit(recipe, frame.loc[rows, columns], target[rows])
            score = model.predict_proba(frame.loc[select, columns])
            ap = float(fm.frontier_metrics(target[select], score)["pr_auc"])
            candidates.append({"recipe": recipe, "window": window, "train_rows": int(rows.sum()),
                               "avg_precision_2025": round(ap, 4), "seconds": round(time.time() - started)})
            fitted[(recipe, window)] = (model, score)
            log(f"{name}: {recipe}/{window} AP 2025 {ap:.4f}")
    best = max(candidates, key=lambda row: row["avg_precision_2025"])
    keys = [("best on 2025", best["recipe"], best["window"])]
    own = (recipes.recipe_of(meta), current_window(meta))
    if own != (best["recipe"], best["window"]) and own[0] in recipes.RECIPES:
        keys.append(("current recipe", *own))

    recent_target, recent_ts = target[recent], frame.loc[recent, "ts"].values
    refits, models = [], {}
    for role, recipe, window in keys:
        staging, staging_score = fitted[(recipe, window)]
        calibrator = calibration.fit_isotonic(staging_score, target[select])
        rows = training_rows(frame, RECENT_YEAR, window).values
        refit = recipes.fit(recipe, frame.loc[rows, columns], target[rows])
        raw = refit.predict_proba(frame.loc[recent, columns])
        probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1)
        refits.append({"role": role, "recipe": recipe, "window": window, "train_rows": int(rows.sum()),
                       "train_years": f"through {RECENT_YEAR - 1}",
                       "before_2025": quality(recent_target, staging.predict_proba(frame.loc[recent, columns]), None, recent_ts),
                       **quality(recent_target, raw, probability, recent_ts)})
        models[role] = (refit, calibrator, raw)
    chosen = max(refits, key=lambda row: row["avg_precision"])
    refit, calibrator, refit_raw = models[chosen["role"]]
    current_raw = current.predict_proba(frame.loc[recent, columns])
    current_calibrator = artifacts.load_calibrator(name)
    current_probability = (np.clip(calibration.apply_isotonic(current_calibrator, current_raw), 0, 1)
                           if current_calibrator is not None else None)

    report = {
        "current": {"recipe": recipes.recipe_of(meta), "train_years": meta["training_period"]["train_years"],
                    **quality(recent_target, current_raw, current_probability, recent_ts)},
        "refit": chosen,
        "refits": refits,
        "candidates_2025": candidates,
        "recent": {"period": f"{RECENT_YEAR}H1", "n": int(recent.sum()), "base_rate": round(float(recent_target.mean()), 4)},
    }
    gain = report["refit"]["avg_precision"] - report["current"]["avg_precision"]
    report["gain_avg_precision"] = round(gain, 4)
    report["promoted"] = bool(promote and gain > MIN_GAIN)
    log(f"{name}: current AP {report['current']['avg_precision']}, refit {report['refit']['avg_precision']}")
    if report["promoted"]:
        save(name, meta, refit, calibrator, report, current_raw, refit_raw)
    return report


def save(name, meta, model, calibrator, report, current_raw, refit_raw):
    window = WINDOWS[report["refit"]["window"]]
    first_year = RECENT_YEAR - window if window else config.TRAIN_YEARS[0]
    bands = {}
    for level, threshold in meta["model_config"].get("risk_level_thresholds", {}).items():
        share = float(np.mean(current_raw >= threshold))
        bands[level] = float(np.quantile(refit_raw, 1 - share)) if share > 0 else float(refit_raw.max())
    model_config = {
        **meta["model_config"],
        "model_name": report["refit"]["recipe"],
        "recipe": report["refit"]["recipe"],
        "calibrated": True,
        "risk_level_thresholds": bands,
        "risk_level_basis": "alert volume of the previous model on 2026H1",
        "calibration": {
            "method": "isotonic",
            "fit_period": f"{SELECTION_YEAR}, same recipe trained through {SELECTION_YEAR - 1}",
            "evaluated_on": f"{RECENT_YEAR}H1",
            "ece_calibrated": report["refit"]["ece"],
        },
    }
    metrics = {"test": {"period": f"{RECENT_YEAR}H1", **report["refit"]}, "previous": report["current"]}
    period = {"train_years": f"{first_year}-{RECENT_YEAR - 1}"}
    artifacts.save_artifact(name, model, meta["feature_columns"], model_config, period, metrics,
                            version=time.strftime("%Y-%m-%d"))
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(name), "calibrator.joblib"))
    config_path = os.path.join(config.ROOT, "configs", "models", f"{name}.json")
    with open(config_path, encoding="utf-8") as handle:
        stored = json.load(handle)
    stored["model"] = model_config
    stored["training_period"] = period
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(stored, handle, indent=2, ensure_ascii=False)
    log(f"{name}: promoted {report['refit']['recipe']}/{report['refit']['window']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--promote", action="store_true", help="replace artifacts that the refit beats")
    parser.add_argument("--only", nargs="*", help="model names to study")
    args = parser.parse_args()
    report = {}
    if os.path.exists(OUTPUT):
        with open(OUTPUT, encoding="utf-8") as handle:
            report = json.load(handle)
    names = args.only or [*DEVICE_MODELS, "flood_24h", "phase_24h"]
    for name, frame, horizon in frames(names):
        report[name] = study(name, frame, horizon, args.promote)
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, ensure_ascii=False)
    log(f"report -> {OUTPUT}")


if __name__ == "__main__":
    main()
