import numpy as np
import pandas as pd

from pipeline import artifacts, features as features_mod


def load_model(device_name):
    return artifacts.load_artifact(device_name)


def build_feature_row(prediction_timestamp, channel_events, channel_episodes, model_config):
    cand_ts = np.array([np.datetime64(pd.Timestamp(prediction_timestamp))])
    ev = channel_events.sort_values("ts")
    ev_ts = ev["ts"].values
    ev_alarm = ev["alarm_flag"].values
    ev_value = ev["raw_value"].values
    fail_starts = np.sort(channel_episodes["episode_start"].values) if len(channel_episodes) else np.array([], dtype="datetime64[s]")

    row = features_mod.compute_features_single(
        cand_ts, ev_ts, ev_alarm, ev_value, fail_starts,
        numeric_mode=model_config.get("numeric_mode", False),
        duty_cycle_mode=model_config.get("duty_cycle_mode", False),
        global_rates=model_config.get("global_rates"),
    )
    return row


def predict(device_name, channel_id, sensor_type, engineering_system_type, prediction_timestamp,
            channel_events, channel_episodes):
    model, meta = load_model(device_name)
    cols = meta["feature_columns"]
    row = build_feature_row(prediction_timestamp, channel_events, channel_episodes, meta["model_config"])
    score = float(model.predict_proba(row[cols])[0])

    risk_level = "low"
    for level, threshold in sorted(meta["model_config"].get("risk_level_thresholds", {}).items(),
                                    key=lambda kv: -kv[1]):
        if score >= threshold:
            risk_level = level
            break

    top_factors = []
    if "feature_importance" in meta["model_config"]:
        importances = meta["model_config"]["feature_importance"]
        ranked = sorted(importances.items(), key=lambda kv: -kv[1])[:5]
        for feat_name, importance in ranked:
            top_factors.append({
                "feature": feat_name,
                "value": float(row[feat_name].iloc[0]) if feat_name in row.columns else None,
                "contribution": importance,
            })

    result = {
        "channel_id": str(channel_id),
        "prediction_timestamp": pd.Timestamp(prediction_timestamp).isoformat(),
        "sensor_type": sensor_type,
        "engineering_system_type": engineering_system_type,
        "risk_score": round(score, 4),
        "risk_level": risk_level,
        "top_factors": top_factors,
        "recommended_action": "schedule_inspection_24h" if risk_level in ("high", "critical") else "monitor",
        "model": {
            "name": meta["model_config"].get("model_name"),
            "version": meta["version"],
            "horizon_hours": meta["model_config"].get("horizon_hours"),
            "trained_on_sensor_type": sensor_type,
            "calibrated": meta["model_config"].get("calibrated", False),
        },
    }
    if meta["model_config"].get("calibrated"):
        result["calibrated_probability"] = round(score, 4)
    return result
