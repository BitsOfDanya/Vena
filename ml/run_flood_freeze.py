import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import brier_score_loss

from pipeline import artifacts, calibration, config, extract, features as features_mod, weather as weather_mod
from pipeline.formal import metrics as fm
from pipeline.targets import evaluation, flood
from pipeline.targets.model_zoo import LightGBMModel

NAME = "flood_24h"
HORIZON_HOURS = 24
TRAIN_END_YEAR = 2023
VALID_YEAR = 2024
RISK_PRECISIONS = {"critical": 0.7, "high": 0.5, "medium": 0.3}
RISK_PERCENTILES = {"critical": 0.001, "high": 0.005, "medium": 0.02}
OUTPUT = os.path.join(config.ROOT, "results", "flood_variants.json")

BASE = list(features_mod.FEATURE_COLUMNS)
DUTY = list(features_mod.DUTY_CYCLE_FEATURE_COLUMNS)
VARIANTS = {
    "events": BASE,
    "events+duty": BASE + DUTY,
    "events+duty+weather": BASE + DUTY + flood.PAST_WEATHER,
    "events+duty+weather+forecast": BASE + DUTY + flood.PAST_WEATHER + flood.FORECAST_WEATHER,
}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score):
    result = fm.frontier_metrics(target, score)
    keys = ("pr_auc", "roc_auc", "recall_at_precision_0.7", "precision_at_recall_0.5")
    return {key: round(float(result[key]), 4) for key in keys} | {"base_rate": round(float(np.mean(target)), 4)}


def risk_bands(target, score):
    scored = pd.DataFrame({"target": target, "score": score})
    bands, basis = {}, {}
    for level, precision in RISK_PRECISIONS.items():
        value = evaluation.previous_fold_threshold(scored, precision)
        if np.isfinite(value):
            bands[level], basis[level] = float(value), f"precision {precision}"
        else:
            bands[level] = float(np.quantile(score, 1 - RISK_PERCENTILES[level]))
            basis[level] = f"top {RISK_PERCENTILES[level]:.1%}"
    bands["high"] = min(bands["high"], bands["critical"])
    bands["medium"] = min(bands["medium"], bands["high"])
    return bands, basis


def main() -> None:
    events = extract.extract_events(config.SENSOR_ALIASES["pump"])
    weather = weather_mod.fetch_weather()
    frame, _, rates = flood.build_frame(events, weather, HORIZON_HOURS)
    year = frame["ts"].dt.year
    train = year <= TRAIN_END_YEAR
    valid = year == VALID_YEAR
    test = (year > VALID_YEAR) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=HORIZON_HOURS))
    log(f"candidates: train {int(train.sum())}, valid {int(valid.sum())}, test {int(test.sum())}")

    report, fitted = {}, {}
    for variant, columns in VARIANTS.items():
        model = LightGBMModel({"n_estimators": 300, "num_leaves": 31, "min_child_samples": 200})
        model.fit(frame.loc[train, columns], frame.loc[train, "target"].values)
        report[variant] = {
            "valid": summary(frame.loc[valid, "target"].values, model.predict_proba(frame.loc[valid, columns])),
            "test": summary(frame.loc[test, "target"].values, model.predict_proba(frame.loc[test, columns])),
        }
        fitted[variant] = model
        log(f"{variant}: valid AP {report[variant]['valid']['pr_auc']}, test AP {report[variant]['test']['pr_auc']}")

    best = max(report, key=lambda name: report[name]["valid"]["pr_auc"])
    model, columns = fitted[best], VARIANTS[best]
    valid_raw = model.predict_proba(frame.loc[valid, columns])
    test_raw = model.predict_proba(frame.loc[test, columns])
    y_valid = frame.loc[valid, "target"].values
    y_test = frame.loc[test, "target"].values
    calibrator = calibration.fit_isotonic(valid_raw, y_valid)
    test_prob = np.clip(calibration.apply_isotonic(calibrator, test_raw), 0, 1)
    ece_raw, _ = calibration.expected_calibration_error(y_test, test_raw)
    ece_cal, _ = calibration.expected_calibration_error(y_test, test_prob)
    bands, basis = risk_bands(y_valid, valid_raw)

    model_config = {
        "model_name": model.name,
        "horizon_hours": HORIZON_HOURS,
        "target_state": flood.FLOOD_STATE,
        "numeric_mode": False,
        "duty_cycle_mode": True,
        "weather_features": any(column in columns for column in flood.PAST_WEATHER),
        "with_neighbors": False,
        "global_rates": rates,
        "calibrated": True,
        "calibration": {
            "method": "isotonic",
            "fit_period": str(VALID_YEAR),
            "evaluated_on": "test 2025-2026H1",
            "brier_raw": round(float(brier_score_loss(y_test, test_raw)), 4),
            "brier_calibrated": round(float(brier_score_loss(y_test, test_prob)), 4),
            "ece_raw": round(float(ece_raw), 4),
            "ece_calibrated": round(float(ece_cal), 4),
        },
        "risk_level_thresholds": bands,
        "risk_level_basis": basis,
        "feature_set": best,
    }
    artifacts.save_artifact(
        NAME, model, columns, model_config,
        {"train_years": f"{config.TRAIN_YEARS[0]}-{TRAIN_END_YEAR}"},
        {"variants": report, "selected": best}, version=time.strftime("%Y-%m-%d"),
    )
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(NAME), "calibrator.joblib"))
    with open(os.path.join(config.ROOT, "configs", "models", f"{NAME}.json"), "w", encoding="utf-8") as handle:
        json.dump({"sensor_type": config.SENSOR_ALIASES["pump"], "tag": "flood", "model": model_config,
                   "feature_columns": columns, "artifact": NAME}, handle, indent=2, ensure_ascii=False)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump({"selected": best, "variants": report}, handle, indent=1, ensure_ascii=False)
    log(f"selected {best}; calibration ECE {model_config['calibration']['ece_raw']} -> "
        f"{model_config['calibration']['ece_calibrated']}")


if __name__ == "__main__":
    main()
