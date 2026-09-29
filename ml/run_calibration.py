"""Calibrate the frozen production models into event probabilities.

Isotonic regression maps a model score to the observed frequency of the target
on the validation period and is checked on the held-out test period, so the API
can report "probability of the event within the horizon" instead of a rank.
Risk levels keep using the raw score: isotonic steps can tie neighbouring scores.

Power Health is trained through 2024, so its calibrator is fitted on 2025 and
evaluated by two-fold cross-fitting over alternate months. Models refitted on
data that includes the calibration year keep the calibrator run_refit_study.py
gave them.
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

from pipeline import artifacts, calibration, config, experiments, extract, recipes
from pipeline.targets import modules

HORIZON_FULL_WINDOW = pd.Timedelta(hours=72)
DEVICE_MODELS = {
    "pump": ["pump_24h", "pump_72h", "pump_baseline_72h"],
    "fan": ["fan_24h", "fan_72h"],
    "smoke": ["smoke_24h"],
}
OUTPUT = os.path.join(config.ROOT, "results", "calibration.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def quality(target, raw, calibrated):
    raw = np.clip(raw, 0, 1)
    ece_raw, _ = calibration.expected_calibration_error(target, raw)
    ece_cal, bins = calibration.expected_calibration_error(target, calibrated)
    return {
        "n": int(len(target)),
        "base_rate": round(float(np.mean(target)), 4),
        "brier_raw": round(float(brier_score_loss(target, raw)), 4),
        "brier_calibrated": round(float(brier_score_loss(target, calibrated)), 4),
        "ece_raw": round(float(ece_raw), 4),
        "ece_calibrated": round(float(ece_cal), 4),
        "reliability": [
            {"n": b["n"], "predicted": round(b["confidence"], 4), "observed": round(b["accuracy"], 4)}
            for b in bins
        ],
    }


def attach(name, calibrator, summary):
    directory = artifacts.artifact_dir(name)
    joblib.dump(calibrator, os.path.join(directory, "calibrator.joblib"))
    meta_path = os.path.join(directory, "meta.json")
    with open(meta_path, encoding="utf-8") as handle:
        meta = json.load(handle)
    meta["model_config"]["calibrated"] = True
    meta["model_config"]["calibration"] = summary
    with open(meta_path, "w", encoding="utf-8") as handle:
        json.dump(meta, handle, indent=2, ensure_ascii=False)
    config_path = os.path.join(config.ROOT, "configs", "models", f"{name}.json")
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as handle:
            model_config = json.load(handle)
        model_config["model"]["calibrated"] = True
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(model_config, handle, indent=2, ensure_ascii=False)


def seen(name, meta, fit_year, report):
    """A model trained through the calibration year keeps its own calibrator."""
    if recipes.train_end_year(meta) < fit_year:
        return False
    report[name] = {"skipped": f"trained through {recipes.train_end_year(meta)}",
                    **meta["model_config"].get("calibration", {})}
    log(f"{name}: trained on {fit_year}, calibrator kept")
    return True


def calibrate_device(device, report):
    names = [name for name in DEVICE_MODELS[device]
             if not seen(name, artifacts.load_artifact(name)[1], config.VALID_YEAR, report)]
    if not names:
        return
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
    frames = {}
    for name in names:
        model, meta = artifacts.load_artifact(name)
        horizon = meta["model_config"]["horizon_hours"]
        if horizon not in frames:
            frames[horizon] = ctx.build(horizon_hours=horizon)
        frame = frames[horizon]
        columns = meta["feature_columns"]
        valid = frame["split"] == "valid"
        test = (frame["split"] == "test") & (frame["ts"] <= frame["ts"].max() - HORIZON_FULL_WINDOW)

        valid_raw = model.predict_proba(frame.loc[valid, columns])
        test_raw = model.predict_proba(frame.loc[test, columns])
        calibrator = calibration.fit_isotonic(valid_raw, frame.loc[valid, "target"].values)
        test_cal = np.clip(calibration.apply_isotonic(calibrator, test_raw), 0, 1)

        summary = {
            "method": "isotonic",
            "fit_period": f"{config.VALID_YEAR}",
            "evaluated_on": "test 2025-2026H1",
            **quality(frame.loc[test, "target"].values, test_raw, test_cal),
        }
        attach(name, calibrator, summary)
        report[name] = summary
        log(f"{name}: ECE {summary['ece_raw']} -> {summary['ece_calibrated']}, "
            f"Brier {summary['brier_raw']} -> {summary['brier_calibrated']}")


def calibrate_phase(report):
    name = "phase_24h"
    model, meta = artifacts.load_artifact(name)
    if seen(name, meta, 2025, report):
        return
    events = extract.extract_events(modules.PHASE_SENSOR)
    frame, _, _ = modules.build_phase_frame(events, horizons=(24,))
    valid = frame.loc[frame["ts"].dt.year == 2025]
    raw = model.predict_proba(valid[meta["feature_columns"]])
    target = valid["any_y24"].values
    fold = (valid["ts"].dt.month % 2).values

    cross = np.zeros(len(raw))
    for part in (0, 1):
        fitted = calibration.fit_isotonic(raw[fold != part], target[fold != part])
        cross[fold == part] = np.clip(calibration.apply_isotonic(fitted, raw[fold == part]), 0, 1)
    calibrator = calibration.fit_isotonic(raw, target)

    summary = {
        "method": "isotonic",
        "fit_period": "2025",
        "evaluated_on": "2025, two-fold cross-fitting by alternate months",
        **quality(target, raw, cross),
    }
    attach(name, calibrator, summary)
    report[name] = summary
    log(f"{name}: ECE {summary['ece_raw']} -> {summary['ece_calibrated']}, "
        f"Brier {summary['brier_raw']} -> {summary['brier_calibrated']}")


def main() -> None:
    report = {}
    for device in DEVICE_MODELS:
        calibrate_device(device, report)
    calibrate_phase(report)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(f"calibration report -> {OUTPUT}")


if __name__ == "__main__":
    main()
