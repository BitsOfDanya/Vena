import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import pandas as pd

from pipeline import artifacts, config, episodes as episodes_mod, extract, inference

DEVICES = [
    ("pump", ["pump_24h", "pump_72h"]),
    ("fan", ["fan_24h", "fan_72h"]),
    ("smoke", ["smoke_24h"]),
]

OUTPUT = os.path.join(config.ROOT, "results", "predictions", "snapshot.json")


def channel_reference():
    reference = extract.channel_dictionary().rename(
        columns={
            "ид_канала_данных": "channel_id",
            "тип_инж_системы": "system_type",
            "тип_датчика": "sensor_type",
            "тег_инженерной_системы": "tag",
            "название_датчика": "name",
        }
    )
    lookup = {}
    for row in reference.itertuples():
        lookup[str(row.channel_id)] = {
            "sensor_type": row.sensor_type,
            "system_type": row.system_type,
            "name": row.name,
            "tag": row.tag,
        }
    return lookup


def risk_level(score, thresholds):
    for level, threshold in sorted(thresholds.items(), key=lambda item: -item[1]):
        if score >= threshold:
            return level
    return "low"


def score_device(device, model_names, prediction_time, limit, reference):
    events = extract.extract_events(config.SENSOR_ALIASES[device])
    events = events.sort_values(["channel_id", "ts"])
    all_episodes = episodes_mod.build_episodes(events)
    counts = events.groupby("channel_id", observed=True).size().sort_values(ascending=False)
    channels = list(counts.index[:limit]) if limit else list(counts.index)

    models = {}
    for name in model_names:
        model, meta = artifacts.load_artifact(name)
        models[name] = (model, meta)

    grouped = {key: frame for key, frame in events.groupby("channel_id", observed=True)}
    episode_groups = {key: frame for key, frame in all_episodes.groupby("channel_id", observed=True)}

    rows = []
    for channel_id in channels:
        channel_events = grouped.get(channel_id)
        if channel_events is None or len(channel_events) < 20:
            continue
        channel_episodes = episode_groups.get(channel_id, all_episodes.iloc[0:0])
        info = reference.get(str(channel_id), {})
        for name, (model, meta) in models.items():
            model_config = meta["model_config"]
            feature_row = inference.build_feature_row(prediction_time, channel_events, channel_episodes, model_config)
            score = float(model.predict_proba(feature_row[meta["feature_columns"]])[0])
            thresholds = model_config.get("risk_level_thresholds", {})
            rows.append(
                {
                    "channel_id": str(channel_id),
                    "device_type": device,
                    "model_id": name,
                    "model_version": meta.get("version"),
                    "horizon_hours": model_config.get("horizon_hours"),
                    "score": round(score, 6),
                    "score_type": "calibrated_probability" if model_config.get("calibrated") else "risk_score",
                    "model_risk_level": risk_level(score, thresholds),
                    "thresholds": thresholds,
                    "last_event_at": channel_events["ts"].max().isoformat(),
                    "event_count_30d": int(
                        (channel_events["ts"] >= pd.Timestamp(prediction_time) - pd.Timedelta(days=30)).sum()
                    ),
                    "failure_count_90d": int(
                        (channel_episodes["episode_start"] >= pd.Timestamp(prediction_time) - pd.Timedelta(days=90)).sum()
                    )
                    if len(channel_episodes)
                    else 0,
                    "factors": {
                        key: float(feature_row[key].iloc[0])
                        for key in ("events_24h", "events_7d", "alarms_24h", "failures_30d", "time_since_last_failure_days")
                        if key in feature_row.columns and pd.notna(feature_row[key].iloc[0])
                    },
                    "sensor_type": info.get("sensor_type"),
                    "system_type": info.get("system_type"),
                    "tag": info.get("tag"),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Score frozen models and write a prediction snapshot")
    parser.add_argument("--limit", type=int, default=0, help="channels per device, 0 for all")
    parser.add_argument("--output", default=OUTPUT)
    arguments = parser.parse_args()

    reference = channel_reference()
    prediction_time = None
    predictions = []
    for device, model_names in DEVICES:
        events = extract.extract_events(config.SENSOR_ALIASES[device])
        device_time = events["ts"].max()
        prediction_time = device_time if prediction_time is None else max(prediction_time, device_time)

    for device, model_names in DEVICES:
        predictions.extend(score_device(device, model_names, prediction_time, arguments.limit, reference))

    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "prediction_time": pd.Timestamp(prediction_time).isoformat(),
        "models": {
            name: {
                "version": artifacts.load_artifact(name)[1].get("version"),
                "horizon_hours": artifacts.load_artifact(name)[1]["model_config"].get("horizon_hours"),
                "calibrated": artifacts.load_artifact(name)[1]["model_config"].get("calibrated", False),
            }
            for _, names in DEVICES
            for name in names
        },
        "predictions": predictions,
    }
    payload["snapshot_id"] = hashlib.sha256(
        json.dumps(payload["predictions"], sort_keys=True).encode()
    ).hexdigest()[:16]

    os.makedirs(os.path.dirname(arguments.output), exist_ok=True)
    with open(arguments.output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    print(f"{len(predictions)} predictions -> {arguments.output} ({payload['snapshot_id']})")


if __name__ == "__main__":
    main()
