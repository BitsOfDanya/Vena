"""Freeze the alarm corroboration model that flags alarms to verify before dispatch.

A detection alarm (smoke, gas, temperature) is corroborated when within 30
minutes it repeats on the channel, another channel of the same tag group alarms,
or the channel stays in the detection state. There is no operator label of true
and false alarms, so an uncorroborated alarm is treated as a candidate false
alarm, not a confirmed one. The operating threshold keeps 90% of corroborated
alarms on the validation year and reports how many uncorroborated alarms it
filters on the held-out first half of 2026.
"""

import json
import os
import time

import joblib
import numpy as np
from sklearn.metrics import brier_score_loss

from pipeline import artifacts, calibration, config
from pipeline.formal import metrics as fm
from pipeline.targets import modules
from pipeline.targets.model_zoo import LightGBMModel

WINDOW = 30
TARGET = f"c{WINDOW}_corroborated"
TRAIN_END_YEAR = 2024
VALID_YEAR = 2025
TEST_YEAR = 2026
KEEP_CORROBORATED = 0.90
NAME = f"alarm_{WINDOW}m"


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def threshold_keeping(target, score, share):
    """Highest score threshold that still keeps `share` of corroborated alarms."""
    positives = np.sort(score[target == 1])
    return float(positives[int(np.floor((1 - share) * len(positives)))])


def operating(target, score, threshold):
    kept = score >= threshold
    corroborated = target == 1
    return {
        "threshold": round(threshold, 4),
        "kept_corroborated": round(float(kept[corroborated].mean()), 4),
        "filtered_uncorroborated": round(float((~kept[~corroborated]).mean()), 4),
        "flagged_share": round(float((~kept).mean()), 4),
        "precision_of_flag": round(float((~corroborated[~kept]).mean()), 4) if (~kept).any() else None,
    }


def main() -> None:
    frame = modules.build_alarm_frame(include_lockbox=True)
    columns = modules.alarm_feature_columns(frame)
    year = frame["ts"].dt.year
    # Labels need the full corroboration window after the alarm.
    complete = frame["ts"] <= frame["ts"].max() - np.timedelta64(WINDOW, "m")
    train, valid, test = (year <= TRAIN_END_YEAR), (year == VALID_YEAR), (year == TEST_YEAR) & complete
    log(f"alarms: train {int(train.sum())}, valid {int(valid.sum())}, test {int(test.sum())}")

    model = LightGBMModel({"n_estimators": 300, "num_leaves": 63})
    model.fit(frame.loc[train, columns], frame.loc[train, TARGET].values)

    valid_raw = model.predict_proba(frame.loc[valid, columns])
    test_raw = model.predict_proba(frame.loc[test, columns])
    y_valid = frame.loc[valid, TARGET].values
    y_test = frame.loc[test, TARGET].values

    calibrator = calibration.fit_isotonic(valid_raw, y_valid)
    test_prob = np.clip(calibration.apply_isotonic(calibrator, test_raw), 0, 1)
    ece_raw, _ = calibration.expected_calibration_error(y_test, test_raw)
    ece_cal, _ = calibration.expected_calibration_error(y_test, test_prob)
    threshold = threshold_keeping(y_valid, valid_raw, KEEP_CORROBORATED)

    metrics = {
        "valid": {k: v for k, v in fm.frontier_metrics(y_valid, valid_raw).items() if k in ("pr_auc", "roc_auc")},
        "test": {k: v for k, v in fm.frontier_metrics(y_test, test_raw).items() if k in ("pr_auc", "roc_auc")},
        "test_base_rate": float(y_test.mean()),
        "operating_valid": operating(y_valid, valid_raw, threshold),
        "operating_test": operating(y_test, test_raw, threshold),
        "calibration": {
            "method": "isotonic",
            "fit_period": str(VALID_YEAR),
            "evaluated_on": "test 2026H1",
            "brier_raw": round(float(brier_score_loss(y_test, test_raw)), 4),
            "brier_calibrated": round(float(brier_score_loss(y_test, test_prob)), 4),
            "ece_raw": round(float(ece_raw), 4),
            "ece_calibrated": round(float(ece_cal), 4),
        },
    }
    model_config = {
        "model_name": model.name,
        "target": TARGET,
        "window_minutes": WINDOW,
        "sensor_types": sorted(frame["sensor_type"].unique().tolist()),
        "calibrated": True,
        "isolated_threshold": threshold,
        "isolated_threshold_basis": f"keeps {KEEP_CORROBORATED:.0%} of corroborated alarms in {VALID_YEAR}",
    }
    artifacts.save_artifact(
        NAME, model, columns, model_config,
        {"train_years": f"{config.TRAIN_YEARS[0]}-{TRAIN_END_YEAR}"}, metrics, version=time.strftime("%Y-%m-%d"),
    )
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(NAME), "calibrator.joblib"))
    log(json.dumps(metrics, indent=1, default=float))


if __name__ == "__main__":
    main()
