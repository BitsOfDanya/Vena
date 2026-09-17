import json
import os
import sys
import time

import numpy as np

from pipeline import config, experiments, training, models as models_mod, decision
from pipeline import alerts as alerts_mod, calibration, error_analysis, artifacts, evaluate


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_final_for_device(sensor_type, tag, horizon_hours, model_name, with_neighbors=False,
                          with_duty_cycle=False, cooldown_hours_options=(24, 48, 72)):
    ctx = experiments.DeviceContext(sensor_type)
    df = ctx.build(horizon_hours=horizon_hours, with_neighbors=with_neighbors)
    cols = training.feature_columns(with_neighbors=with_neighbors, with_duty_cycle=with_duty_cycle)

    train = df[df["split"] == "train"]
    valid = df[df["split"] == "valid"]
    test = df[df["split"] == "test"]

    model = models_mod.MODEL_REGISTRY[model_name]()
    model.fit(train[cols], train["target"])

    valid_score = model.predict_proba(valid[cols])
    test_score = model.predict_proba(test[cols])

    metrics_valid = evaluate.evaluate(valid["target"].values, valid_score)
    metrics_test = evaluate.evaluate(test["target"].values, test_score)
    daily_valid = evaluate.evaluate_daily_topk(valid["ts"].values, valid["target"].values, valid_score)
    daily_test = evaluate.evaluate_daily_topk(test["ts"].values, test["target"].values, test_score)
    fixed_test = evaluate.evaluate_daily_topk_fixed(test["ts"].values, test["target"].values, test_score)

    formal_results = {}
    frozen_recall = decision.freeze_threshold_max_recall_at_precision(valid["target"].values, valid_score, 0.7)
    if frozen_recall:
        applied = decision.apply_frozen_threshold(test["target"].values, test_score, frozen_recall["threshold"])
        formal_results["max_recall_at_precision_0.7"] = {"frozen_on_valid": frozen_recall, "applied_on_test": applied}
    frozen_precision = decision.freeze_threshold_max_precision_at_recall(valid["target"].values, valid_score, 0.5)
    if frozen_precision:
        applied2 = decision.apply_frozen_threshold(test["target"].values, test_score, frozen_precision["threshold"])
        formal_results["max_precision_at_recall_0.5"] = {"frozen_on_valid": frozen_precision, "applied_on_test": applied2}

    test_with_score = test.copy()
    test_with_score["_score"] = test_score
    test_episodes = ctx.episodes[ctx.episodes["episode_start"].dt.year >= config.TEST_YEARS[0]]
    n_days_test = max((test["ts"].max() - test["ts"].min()).total_seconds() / 86400.0, 1.0)

    alert_results = {}
    last_alerts_for_error_analysis = None
    for cooldown in cooldown_hours_options:
        raw_topk = alerts_mod.raw_daily_topk(test_with_score, "_score", 0.01, mode="frac")
        alerts_topk = alerts_mod._apply_cooldown(raw_topk, cooldown)
        summary = alerts_mod.alert_summary(alerts_topk, raw_topk, test_episodes, horizon_hours, n_days_test)
        alert_results[f"cooldown_{cooldown}h"] = summary
        if cooldown == 24:
            last_alerts_for_error_analysis = alerts_topk

    cal = calibration.calibrate_and_evaluate(model, valid, test, cols, method="isotonic")

    threshold_for_error = frozen_recall["threshold"] if frozen_recall else float(np.percentile(test_score, 99))
    fn_stats = error_analysis.fn_breakdown(test[["channel_id", "ts"]], test_episodes, horizon_hours,
                                            last_alerts_for_error_analysis)
    fp_stats = error_analysis.fp_near_miss_summary(test_with_score, "_score", threshold_for_error,
                                                     ctx.episodes, horizon_hours)

    metrics_snapshot = {
        "valid": metrics_valid, "test": metrics_test,
        "daily_valid": daily_valid, "daily_test": daily_test, "fixed_topk_test": fixed_test,
        "formal_70_50": formal_results, "alerts": alert_results,
        "calibration": {"method": cal["method"], "brier_raw": cal["brier_raw"], "brier_calibrated": cal["brier_calibrated"],
                        "ece_raw": cal["ece_raw"], "ece_calibrated": cal["ece_calibrated"]},
        "fn_breakdown": fn_stats, "fp_near_miss": fp_stats,
    }

    risk_thresholds = {}
    for level in ["critical", "high", "medium"]:
        pct = {"critical": 0.001, "high": 0.005, "medium": 0.02}[level]
        risk_thresholds[level] = float(np.quantile(test_score, 1 - pct))

    model_config = {
        "model_name": model_name, "horizon_hours": horizon_hours,
        "numeric_mode": sensor_type in config.NUMERIC_DOMINANT_SENSOR_TYPES,
        "duty_cycle_mode": with_duty_cycle and sensor_type in config.DUTY_CYCLE_SENSOR_TYPES,
        "with_neighbors": with_neighbors,
        "global_rates": ctx.global_rates,
        "calibrated": False,
        "risk_level_thresholds": risk_thresholds,
    }

    artifact_name = f"{tag}_{horizon_hours}h"
    artifacts.save_artifact(
        artifact_name, model, cols, model_config,
        {"train_years": f"{config.TRAIN_YEARS[0]}-{config.TRAIN_YEARS[1]}"},
        metrics_snapshot, version=time.strftime("%Y-%m-%d"),
    )

    os.makedirs(os.path.join(config.ROOT, "configs", "models"), exist_ok=True)
    with open(os.path.join(config.ROOT, "configs", "models", f"{tag}_{horizon_hours}h.json"), "w") as f:
        json.dump({
            "sensor_type": sensor_type, "tag": tag, "model": model_config,
            "feature_columns": cols, "artifact": artifact_name,
        }, f, indent=2, ensure_ascii=False)

    return metrics_snapshot


def main():
    device = sys.argv[1]
    horizon_hours = int(sys.argv[2])
    model_name = sys.argv[3]
    with_neighbors = "--with-neighbors" in sys.argv
    with_duty_cycle = "--with-duty-cycle" in sys.argv

    devices = {"pump": "Состояние насоса", "fan": "Состояние вентилятора", "smoke": "Датчик дыма"}
    sensor_type = devices[device]

    log(f"final freeze {device} {horizon_hours}h {model_name} start")
    snapshot = run_final_for_device(sensor_type, device, horizon_hours, model_name,
                                     with_neighbors=with_neighbors, with_duty_cycle=with_duty_cycle)
    with open(f"analysis/tables/final_snapshot_{device}_{horizon_hours}h.json", "w") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False, default=str)
    log(f"final freeze {device} {horizon_hours}h {model_name} done")


if __name__ == "__main__":
    main()
