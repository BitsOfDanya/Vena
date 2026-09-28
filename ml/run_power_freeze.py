import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, config, extract, training
from pipeline.formal import metrics as fm
from pipeline.targets import evaluation, model_zoo, modules, state_target

TAG = "phase"
HORIZON_HOURS = 24
TRAIN_END_YEAR = 2024
VALID_YEAR = 2025
TARGET_COLUMN = "any_y24"
RISK_PERCENTILES = {"critical": 0.001, "high": 0.005, "medium": 0.02}
# Power loss has a 29% base rate, so tail quantiles land far above any operating
# point: the threshold that reaches precision 0.70 is around 0.47 while the top 2%
# quantile is above 0.99. Bands are therefore anchored to measured precision.
RISK_PRECISIONS = {"critical": 0.9, "high": 0.7, "medium": 0.5}


def percentile_thresholds(score):
    return {level: float(np.quantile(score, 1 - pct)) for level, pct in RISK_PERCENTILES.items()}


def precision_thresholds(target, score):
    frame = pd.DataFrame({"target": target, "score": score})
    thresholds = {}
    for level, precision in RISK_PRECISIONS.items():
        value = evaluation.previous_fold_threshold(frame, precision)
        if not np.isfinite(value):
            value = float(np.quantile(score, 0.999))
        thresholds[level] = float(value)
    return thresholds


def main() -> None:
    events = extract.extract_events(modules.PHASE_SENSOR)
    frame, episodes, _ = modules.build_phase_frame(events, horizons=(HORIZON_HOURS,))
    columns = training.feature_columns()

    year = frame["ts"].dt.year
    train_mask = (year <= TRAIN_END_YEAR).values
    valid_mask = (year == VALID_YEAR).values

    model = model_zoo.LightGBMModel({"n_estimators": 300, "num_leaves": 63})
    model.fit(frame.loc[train_mask, columns], frame.loc[train_mask, TARGET_COLUMN].values)

    valid = frame.loc[valid_mask].copy()
    valid_score = model.predict_proba(valid[columns])
    valid_target = valid[TARGET_COLUMN].values

    frontier = fm.frontier_metrics(valid_target, valid_score)
    threshold = evaluation.previous_fold_threshold(
        pd.DataFrame({"target": valid_target, "score": valid_score}), 0.7
    )
    scored = valid[["channel_id", "ts"]].assign(target=valid_target, score=valid_score)
    operating_point = evaluation.operating_point_report(scored, threshold, episodes, HORIZON_HOURS)

    metrics_snapshot = {
        "valid": frontier,
        "operating_point_precision_0.70": operating_point,
        "frozen_threshold": float(threshold),
        "target": TARGET_COLUMN,
        "target_state": modules.PHASE_STATE,
        "train_end_year": TRAIN_END_YEAR,
        "valid_year": VALID_YEAR,
        "n_train": int(train_mask.sum()),
        "n_valid": int(valid_mask.sum()),
        "base_rate": float(valid_target.mean()),
        "channels": int(frame["channel_id"].nunique()),
        "risk_level_thresholds_percentile": percentile_thresholds(valid_score),
    }

    model_config = {
        "model_name": model.name,
        "horizon_hours": HORIZON_HOURS,
        "numeric_mode": False,
        "duty_cycle_mode": False,
        "with_neighbors": False,
        "target_state": modules.PHASE_STATE,
        "global_rates": state_target.global_rates(events, modules.PHASE_STATE, config.TRAIN_YEARS[1]),
        "calibrated": False,
        "risk_level_thresholds": precision_thresholds(valid_target, valid_score),
        "risk_level_basis": "validation precision targets 0.9 / 0.7 / 0.5",
    }

    artifact_name = f"{TAG}_{HORIZON_HOURS}h"
    artifacts.save_artifact(
        artifact_name,
        model,
        columns,
        model_config,
        {"train_years": f"{config.TRAIN_YEARS[0]}-{TRAIN_END_YEAR}"},
        metrics_snapshot,
        version=time.strftime("%Y-%m-%d"),
    )

    os.makedirs(os.path.join(config.ROOT, "configs", "models"), exist_ok=True)
    config_path = os.path.join(config.ROOT, "configs", "models", f"{artifact_name}.json")
    with open(config_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "sensor_type": modules.PHASE_SENSOR,
                "tag": TAG,
                "device": TAG,
                "horizon": f"{HORIZON_HOURS}h",
                "model": model_config,
                "feature_columns": columns,
                "artifact": artifact_name,
                "training_period": {"train_years": f"{config.TRAIN_YEARS[0]}-{TRAIN_END_YEAR}"},
                "version": time.strftime("%Y-%m-%d"),
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    print(json.dumps({
        "artifact": artifact_name,
        "channels": metrics_snapshot["channels"],
        "base_rate": round(metrics_snapshot["base_rate"], 4),
        "pr_auc": round(frontier["pr_auc"], 4),
        "roc_auc": round(frontier["roc_auc"], 4),
        "recall_at_precision_0.7": round(frontier["recall_at_precision_0.7"], 4),
        "precision_at_recall_0.5": round(frontier["precision_at_recall_0.5"], 4),
        "alert_precision_dedup": round(operating_point["alert_precision_dedup"], 4),
        "episode_recall": round(operating_point["episode_recall"], 4),
        "alerts_per_day": round(operating_point["alerts_per_day"], 2),
        "median_lead_time_hours": round(operating_point["median_lead_time_hours"], 2),
        "risk_level_thresholds": {k: round(v, 4) for k, v in model_config["risk_level_thresholds"].items()},
    }, indent=1))


if __name__ == "__main__":
    main()
