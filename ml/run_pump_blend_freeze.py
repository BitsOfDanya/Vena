import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, config, evaluate, experiments, training
from pipeline.ensemble import ProbabilityBlend
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

TAG = "pump"
HORIZON_HOURS = 72
WINDOW_YEARS = 3
EMBARGO_HOURS = 168
LINEAR_WEIGHT = 0.5
TREE_PARAMS = {"num_leaves": 7, "min_child_samples": 500}
MIN_HISTORY_DAYS = 30
FALLBACK_ARTIFACT = "pump_baseline_72h"
RISK_PERCENTILES = {"critical": 0.001, "high": 0.005, "medium": 0.02}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES[TAG])
    frame = ctx.build(horizon_hours=HORIZON_HOURS)
    columns = training.feature_columns()

    valid_start = pd.Timestamp(f"{config.VALID_YEAR}-01-01")
    train = (frame["split"] == "train") & (frame["ts"] < valid_start - pd.Timedelta(hours=EMBARGO_HOURS))
    train &= frame["ts"].dt.year > config.TRAIN_YEARS[1] - WINDOW_YEARS
    valid = frame["split"] == "valid"
    test = frame["split"] == "test"
    test &= frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=HORIZON_HOURS)

    log(f"fit on {int(train.sum())} rows")
    linear = LogisticRegressionModel().fit(frame.loc[train, columns], frame.loc[train, "target"])
    tree = LightGBMModel(TREE_PARAMS).fit(frame.loc[train, columns], frame.loc[train, "target"])
    model = ProbabilityBlend(linear, tree, linear_weight=LINEAR_WEIGHT)

    valid_score = model.predict_proba(frame.loc[valid, columns])
    test_score = model.predict_proba(frame.loc[test, columns])
    metrics_valid = evaluate.evaluate(frame.loc[valid, "target"].values, valid_score)
    metrics_test = evaluate.evaluate(frame.loc[test, "target"].values, test_score)

    _, baseline_meta = artifacts.load_artifact(FALLBACK_ARTIFACT)
    baseline_ap = baseline_meta["metrics_snapshot"]["test"]["avg_precision"]
    log(f"blend test AP {metrics_test['avg_precision']:.4f} vs baseline {baseline_ap:.4f}")
    if metrics_test["avg_precision"] <= baseline_ap:
        raise SystemExit("blend does not beat the baseline on the test period; pump_72h left unchanged")

    model_config = {
        "model_name": "blend_lr_lightgbm",
        "horizon_hours": HORIZON_HOURS,
        "numeric_mode": False,
        "duty_cycle_mode": False,
        "with_neighbors": False,
        "global_rates": ctx.global_rates,
        "calibrated": False,
        "risk_level_thresholds": {
            level: float(np.quantile(test_score, 1 - pct)) for level, pct in RISK_PERCENTILES.items()
        },
        "linear_weight": LINEAR_WEIGHT,
        "tree_params": TREE_PARAMS,
        "window_years": WINDOW_YEARS,
        "fallback_artifact": FALLBACK_ARTIFACT,
        "min_history_days": MIN_HISTORY_DAYS,
    }
    metrics_snapshot = {
        "valid": metrics_valid,
        "test": metrics_test,
        "baseline_test_avg_precision": baseline_ap,
    }
    artifact_name = f"{TAG}_{HORIZON_HOURS}h"
    training_period = {"train_years": f"{config.TRAIN_YEARS[1] - WINDOW_YEARS + 1}-{config.TRAIN_YEARS[1]}"}
    artifacts.save_artifact(
        artifact_name, model, columns, model_config, training_period, metrics_snapshot,
        version=time.strftime("%Y-%m-%d"),
    )
    with open(os.path.join(config.ROOT, "configs", "models", f"{artifact_name}.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "sensor_type": config.SENSOR_ALIASES[TAG],
                "tag": TAG,
                "model": model_config,
                "feature_columns": columns,
                "artifact": artifact_name,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
    log(json.dumps({
        "artifact": artifact_name,
        "valid_ap": round(metrics_valid["avg_precision"], 4),
        "test_ap": round(metrics_test["avg_precision"], 4),
        "baseline_test_ap": round(baseline_ap, 4),
        "test_recall_at_p70": round(metrics_test["recall_at_precision_0.7"], 4),
    }))


if __name__ == "__main__":
    main()
