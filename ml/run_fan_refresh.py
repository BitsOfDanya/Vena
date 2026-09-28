"""Refit the fan models on all history through 2025.

The fan score distribution drifted strongly between 2024 and 2026H1 (population
stability index about 1.0, results/model_report.json), so the fan models are
refitted with their recipe (CatBoost) on 2019-2025 and evaluated on 2026H1.
The calibrator cannot be fitted on 2025 once the model has seen it, so it comes
from the same recipe trained through 2024 and scored on 2025; its quality is
checked on 2026H1 with the final model.
"""

import json
import os
import time

import joblib
import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, experiments, training
from pipeline.formal import metrics as fm
from pipeline.models import CatBoostModel

EMBARGO = pd.Timedelta(hours=168)
RISK_PERCENTILES = {"critical": 0.001, "high": 0.005, "medium": 0.02}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def fit(frame, columns, before):
    train = frame["ts"] < pd.Timestamp(before) - EMBARGO
    return CatBoostModel().fit(frame.loc[train, columns], frame.loc[train, "target"])


def main() -> None:
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES["fan"])
    columns = training.feature_columns()
    for horizon in (24, 72):
        name = f"fan_{horizon}h"
        frame = ctx.build(horizon_hours=horizon)
        year = frame["ts"].dt.year
        valid = year == 2025
        test = (year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon))

        staging = fit(frame, columns, "2025-01-01")
        calibrator = calibration.fit_isotonic(
            staging.predict_proba(frame.loc[valid, columns]), frame.loc[valid, "target"].values
        )
        model = fit(frame, columns, "2026-01-01")
        raw = model.predict_proba(frame.loc[test, columns])
        target = frame.loc[test, "target"].values
        probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1)
        frontier = fm.frontier_metrics(target, raw)
        ece, _ = calibration.expected_calibration_error(target, probability)

        _, previous = artifacts.load_artifact(name)
        model_config = {
            **previous["model_config"],
            "global_rates": ctx.global_rates,
            "calibrated": True,
            "risk_level_thresholds": {level: float(np.quantile(raw, 1 - pct)) for level, pct in RISK_PERCENTILES.items()},
            "calibration": {
                "method": "isotonic",
                "fit_period": "2025, model trained through 2024",
                "evaluated_on": "2026H1",
                "ece_calibrated": round(float(ece), 4),
                "predicted": round(float(probability.mean()), 4),
                "observed": round(float(target.mean()), 4),
            },
        }
        metrics = {
            "test": {
                "period": "2026H1",
                "n": int(test.sum()),
                "n_positive": int(target.sum()),
                "avg_precision": float(frontier["pr_auc"]),
                "roc_auc": float(frontier["roc_auc"]),
                "recall_at_precision_0.7": float(frontier["recall_at_precision_0.7"]),
                "precision_at_recall_0.5": float(frontier["precision_at_recall_0.5"]),
            },
            "previous_test_avg_precision": previous["metrics_snapshot"]["test"]["avg_precision"],
            "reason": "score drift between 2024 and 2026H1, PSI about 1.0",
        }
        artifacts.save_artifact(
            name, model, columns, model_config, {"train_years": "2019-2025"}, metrics, version=time.strftime("%Y-%m-%d")
        )
        joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(name), "calibrator.joblib"))
        config_path = os.path.join(config.ROOT, "configs", "models", f"{name}.json")
        with open(config_path, encoding="utf-8") as handle:
            stored = json.load(handle)
        stored["model"] = model_config
        stored["training_period"] = {"train_years": "2019-2025"}
        with open(config_path, "w", encoding="utf-8") as handle:
            json.dump(stored, handle, indent=2, ensure_ascii=False)
        log(f"{name}: AP {frontier['pr_auc']:.4f}, ROC {frontier['roc_auc']:.4f}, ECE {ece:.4f}")


if __name__ == "__main__":
    main()
