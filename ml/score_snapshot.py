import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from pipeline import artifacts, config, episodes as episodes_mod, inference

DEVICES = [
    ("pump", ["pump_24h", "pump_72h"]),
    ("fan", ["fan_24h", "fan_72h"]),
    ("smoke", ["smoke_24h"]),
]

OUTPUT = os.path.join(config.ROOT, "results", "predictions", "snapshot.json")

# Asset IDs match frontend/src/entities/infrastructure/fixtures/demo.ts
DEMO_CHANNELS = {
    "pump": [
        ("P-0142", "critical"),
        ("P-0106", "high"),
        ("P-0111", "medium"),
        ("P-0116", "low"),
        ("P-0121", "low"),
        ("P-0126", "medium"),
    ],
    "fan": [
        ("F-0102", "high"),
        ("F-0107", "medium"),
        ("F-0112", "low"),
        ("F-0117", "critical"),
        ("F-0122", "low"),
        ("F-0312", "medium"),
    ],
    "smoke": [
        ("S-0103", "high"),
        ("S-0108", "medium"),
        ("S-0113", "low"),
        ("S-0118", "critical"),
        ("S-4412", "medium"),
    ],
}

DEMO_META = {
    "pump": {"sensor_type": "Состояние насоса", "system_type": "Водоотведение", "tag": "demo-pump"},
    "fan": {"sensor_type": "Состояние вентилятора", "system_type": "Вентиляция", "tag": "demo-fan"},
    "smoke": {"sensor_type": "Датчик дыма", "system_type": "Пожарная система", "tag": "demo-smoke"},
}

PROFILE_PARAMS = {
    "critical": {"events": 400, "alarm_rate": 0.45, "fault_rate": 0.28, "burst_hours": 6},
    "high": {"events": 280, "alarm_rate": 0.32, "fault_rate": 0.18, "burst_hours": 12},
    "medium": {"events": 140, "alarm_rate": 0.15, "fault_rate": 0.06, "burst_hours": 48},
    "low": {"events": 45, "alarm_rate": 0.03, "fault_rate": 0.005, "burst_hours": 240},
}


def channel_reference():
    from pipeline import extract

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


def _synthetic_channel_events(channel_id, prediction_time, profile, seed):
    params = PROFILE_PARAMS[profile]
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(prediction_time)
    start = end - pd.Timedelta(days=90)
    span_hours = max((end - start) / pd.Timedelta(hours=1), 1.0)
    offsets = np.sort(rng.uniform(0, span_hours, size=params["events"]))
    # denser activity near the end for higher-risk profiles
    burst_start = span_hours - params["burst_hours"]
    if profile != "low":
        extra = rng.uniform(burst_start, span_hours, size=max(params["events"] // 3, 8))
        offsets = np.sort(np.concatenate([offsets, extra]))
    timestamps = start + pd.to_timedelta(offsets, unit="h")

    values = []
    alarms = []
    for offset in offsets:
        roll = rng.random()
        in_burst = offset >= burst_start
        fault_p = params["fault_rate"] * (2.5 if in_burst else 1.0)
        alarm_p = params["alarm_rate"] * (2.0 if in_burst else 1.0)
        if roll < fault_p:
            values.append(config.FAULT_LITERAL)
            alarms.append(1)
        elif roll < fault_p + alarm_p:
            values.append("Тревога")
            alarms.append(1)
        else:
            values.append(rng.choice(["Норма", "Включен", "Выключен"]))
            alarms.append(0)

    return pd.DataFrame(
        {
            "channel_id": channel_id,
            "ts": timestamps,
            "alarm_flag": alarms,
            "raw_value": values,
        }
    )


def build_demo_events(prediction_time):
    frames = []
    seed = 0
    for device, channels in DEMO_CHANNELS.items():
        for channel_id, profile in channels:
            frames.append(_synthetic_channel_events(channel_id, prediction_time, profile, seed))
            seed += 1
    return pd.concat(frames, ignore_index=True)


def score_rows(device, model_names, prediction_time, events, reference):
    events = events.sort_values(["channel_id", "ts"])
    all_episodes = episodes_mod.build_episodes(events)
    models = {}
    for name in model_names:
        model, meta = artifacts.load_artifact(name)
        models[name] = (model, meta)

    grouped = {key: frame for key, frame in events.groupby("channel_id", observed=True)}
    episode_groups = {key: frame for key, frame in all_episodes.groupby("channel_id", observed=True)}
    fallback = DEMO_META.get(device, {})

    rows = []
    for channel_id, channel_events in grouped.items():
        if len(channel_events) < 20:
            continue
        channel_episodes = episode_groups.get(channel_id, all_episodes.iloc[0:0])
        info = reference.get(str(channel_id), fallback)
        for name, (model, meta) in models.items():
            model_config = meta["model_config"]
            feature_row = inference.build_feature_row(
                prediction_time, channel_events, channel_episodes, model_config
            )
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
                    "score_type": "calibrated_probability"
                    if model_config.get("calibrated")
                    else "risk_score",
                    "model_risk_level": risk_level(score, thresholds),
                    "thresholds": thresholds,
                    "last_event_at": channel_events["ts"].max().isoformat(),
                    "event_count_30d": int(
                        (
                            channel_events["ts"]
                            >= pd.Timestamp(prediction_time) - pd.Timedelta(days=30)
                        ).sum()
                    ),
                    "failure_count_90d": int(
                        (
                            channel_episodes["episode_start"]
                            >= pd.Timestamp(prediction_time) - pd.Timedelta(days=90)
                        ).sum()
                    )
                    if len(channel_episodes)
                    else 0,
                    "factors": {
                        key: float(feature_row[key].iloc[0])
                        for key in (
                            "events_24h",
                            "events_7d",
                            "alarms_24h",
                            "failures_30d",
                            "time_since_last_failure_days",
                        )
                        if key in feature_row.columns and pd.notna(feature_row[key].iloc[0])
                    },
                    "sensor_type": info.get("sensor_type"),
                    "system_type": info.get("system_type"),
                    "tag": info.get("tag"),
                }
            )
    return rows


def score_device(device, model_names, prediction_time, limit, reference):
    from pipeline import extract

    events = extract.extract_events(config.SENSOR_ALIASES[device])
    counts = events.groupby("channel_id", observed=True).size().sort_values(ascending=False)
    channels = list(counts.index[:limit]) if limit else list(counts.index)
    events = events[events["channel_id"].isin(channels)]
    return score_rows(device, model_names, prediction_time, events, reference)


def write_snapshot(predictions, prediction_time, output):
    model_info = {}
    for _, names in DEVICES:
        for name in names:
            _, meta = artifacts.load_artifact(name)
            model_info[name] = {
                "version": meta.get("version"),
                "horizon_hours": meta["model_config"].get("horizon_hours"),
                "calibrated": meta["model_config"].get("calibrated", False),
            }
    payload = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "prediction_time": pd.Timestamp(prediction_time).isoformat(),
        "models": model_info,
        "predictions": predictions,
    }
    payload["snapshot_id"] = hashlib.sha256(
        json.dumps(payload["predictions"], sort_keys=True).encode()
    ).hexdigest()[:16]

    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    print(f"{len(predictions)} predictions -> {output} ({payload['snapshot_id']})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score frozen models and write a prediction snapshot")
    parser.add_argument("--limit", type=int, default=0, help="channels per device, 0 for all")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="score synthetic demo channels with frozen models (no journal dataset required)",
    )
    parser.add_argument("--output", default=OUTPUT)
    arguments = parser.parse_args()

    if arguments.demo:
        prediction_time = pd.Timestamp(datetime.now(tz=timezone.utc)).tz_localize(None)
        demo_events = build_demo_events(prediction_time)
        predictions = []
        for device, model_names in DEVICES:
            device_ids = {channel_id for channel_id, _ in DEMO_CHANNELS[device]}
            events = demo_events[demo_events["channel_id"].isin(device_ids)]
            predictions.extend(score_rows(device, model_names, prediction_time, events, {}))
        write_snapshot(predictions, prediction_time, arguments.output)
        return

    from pipeline import extract

    reference = channel_reference()
    prediction_time = None
    predictions = []
    for device, model_names in DEVICES:
        events = extract.extract_events(config.SENSOR_ALIASES[device])
        device_time = events["ts"].max()
        prediction_time = device_time if prediction_time is None else max(prediction_time, device_time)

    for device, model_names in DEVICES:
        predictions.extend(
            score_device(device, model_names, prediction_time, arguments.limit, reference)
        )

    write_snapshot(predictions, prediction_time, arguments.output)


if __name__ == "__main__":
    main()
