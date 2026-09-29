import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, episodes as episodes_mod, explain, inference
from pipeline.locations import location_group
from pipeline.targets import access, discovery, flood

DEVICES = [
    ("pump", ["pump_24h", "pump_72h"], config.FAULT_LITERAL),
    ("fan", ["fan_24h", "fan_72h"], config.FAULT_LITERAL),
    ("smoke", ["smoke_24h"], config.FAULT_LITERAL),
    ("phase", ["phase_24h"], "Обесточен"),
    ("flood", ["flood_24h"], flood.FLOOD_STATE),
]

if os.path.exists(os.path.join(artifacts.artifact_dir("smoke_alarm_24h"), "meta.json")):
    DEVICES.append(("smoke_alarm", ["smoke_alarm_24h"], "Обнаружен дым"))

DEVICE_SENSOR = {"flood": "pump", "smoke_alarm": "smoke"}

SCENARIOS = {
    "pump": "flooding",
    "fan": "ventilation",
    "smoke": "fire",
    "smoke_alarm": "fire",
    "phase": "power_loss",
    "flood": "flooding",
}

RECENT_DAYS = 30
INCIDENT_MODEL = "phase_24h"
PROBABILITY_RANGE = (0.001, 0.99)
ALARM_MODEL = "alarm_30m"
ACCESS_CONFIG = os.path.join(config.ROOT, "configs", "access.json")

OUTPUT = os.path.join(config.ROOT, "results", "predictions", "snapshot.json")

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
            "ид_объект": "object_id",
        }
    )
    if "object_id" not in reference:
        reference["object_id"] = None
    lookup = {}
    for row in reference.itertuples():
        lookup[str(row.channel_id)] = {
            "sensor_type": row.sensor_type,
            "system_type": row.system_type,
            "name": row.name,
            "tag": row.tag,
            "object_id": row.object_id,
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
    for channels in DEMO_CHANNELS.values():
        for channel_id, profile in channels:
            frames.append(_synthetic_channel_events(channel_id, prediction_time, profile, seed))
            seed += 1
    return pd.concat(frames, ignore_index=True)


def build_episodes(events, target_state):
    if target_state == config.FAULT_LITERAL:
        return episodes_mod.build_episodes(events)
    return discovery.state_episodes(events, target_state)


def sensor_of(device):
    return config.SENSOR_ALIASES[DEVICE_SENSOR.get(device, device)]


def calibrated(calibrator, score):
    if calibrator is None:
        return score
    return float(np.clip(calibration.apply_isotonic(calibrator, [score])[0], *PROBABILITY_RANGE))


def score_rows(device, model_names, target_state, events, reference):
    events = events.sort_values(["channel_id", "ts"])
    all_episodes = build_episodes(events, target_state)
    models = {}
    fallbacks = {}
    calibrators = {}
    weather = None
    for name in model_names:
        model, meta = artifacts.load_artifact(name)
        models[name] = (model, meta)
        calibrators[name] = artifacts.load_calibrator(name)
        fallback = meta["model_config"].get("fallback_artifact")
        if fallback:
            fallbacks[name] = artifacts.load_artifact(fallback)
            calibrators[fallback] = artifacts.load_calibrator(fallback)
        if meta["model_config"].get("weather_features"):
            from pipeline import weather as weather_mod

            weather = weather_mod.fetch_weather()

    grouped = {key: frame for key, frame in events.groupby("channel_id", observed=True)}
    episode_groups = {key: frame for key, frame in all_episodes.groupby("channel_id", observed=True)}
    fallback = DEMO_META.get(device, {})

    rows = []
    for channel_id, channel_events in grouped.items():
        if len(channel_events) < 20:
            continue
        channel_episodes = episode_groups.get(channel_id, all_episodes.iloc[0:0])
        info = reference.get(str(channel_id), fallback)
        channel_time = channel_events["ts"].max()
        history_days = (channel_time - channel_events["ts"].min()) / pd.Timedelta(days=1)
        for name, (primary, primary_meta) in models.items():
            model, meta, variant, source = primary, primary_meta, "primary", name
            if name in fallbacks and history_days < primary_meta["model_config"].get("min_history_days", 0):
                model, meta = fallbacks[name]
                variant, source = "fallback", primary_meta["model_config"]["fallback_artifact"]
            model_config = meta["model_config"]
            feature_row = inference.build_feature_row(
                channel_time, channel_events, channel_episodes, model_config
            )
            if model_config.get("weather_features"):
                feature_row = flood.attach_to_row(feature_row, channel_time, weather)
            raw = float(model.predict_proba(feature_row[meta["feature_columns"]])[0])
            probability = calibrated(calibrators.get(source), raw)
            drivers = explain.drivers(model, feature_row[meta["feature_columns"]])
            thresholds = model_config.get("risk_level_thresholds", {})
            rows.append(
                {
                    "channel_id": str(channel_id),
                    "device_type": device,
                    "model_id": name,
                    "model_version": primary_meta.get("version"),
                    "model_variant": variant,
                    "scenario": SCENARIOS.get(device),
                    "horizon_hours": model_config.get("horizon_hours"),
                    "score": round(probability, 6),
                    "raw_score": round(raw, 6),
                    "score_type": "calibrated_probability"
                    if calibrators.get(source) is not None
                    else "risk_score",
                    "model_risk_level": risk_level(raw, thresholds),
                    "thresholds": thresholds,
                    "last_event_at": channel_time.isoformat(),
                    "scored_at": channel_time.isoformat(),
                    "event_count_30d": int(
                        (
                            channel_events["ts"]
                            >= channel_time - pd.Timedelta(days=30)
                        ).sum()
                    ),
                    "failure_count_90d": int(
                        (
                            channel_episodes["episode_start"]
                            >= channel_time - pd.Timedelta(days=90)
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
                    "object_id": info.get("object_id"),
                    "name": info.get("name"),
                    "drivers": drivers,
                }
            )
    return rows


def score_device(device, model_names, target_state, limit, reference):
    from pipeline import extract

    events = extract.extract_events(sensor_of(device))
    counts = events.groupby("channel_id", observed=True).size().sort_values(ascending=False)
    channels = list(counts.index[:limit]) if limit else list(counts.index)
    events = events[events["channel_id"].isin(channels)]
    return score_rows(device, model_names, target_state, events, reference)


def location_history(events_by_sensor, reference, until):
    tags = {key: value.get("tag") for key, value in reference.items()}
    history = {}
    for device, _, target_state in DEVICES:
        events = events_by_sensor.get(sensor_of(device))
        if events is None or events.empty:
            continue
        episodes = build_episodes(events, target_state)
        if episodes.empty:
            continue
        episodes = episodes.assign(group=episodes["channel_id"].astype(str).map(tags).map(location_group))
        episodes = episodes.dropna(subset=["group"])
        recent = episodes.loc[episodes["episode_start"] > until - pd.Timedelta(days=365)]
        duration = (recent["episode_end"] - recent["episode_start"]).dt.total_seconds() / 60
        for group, part in recent.assign(duration=duration).groupby("group"):
            history.setdefault(group, {})[device] = {
                "episodes_365d": int(len(part)),
                "channels": int(part["channel_id"].nunique()),
                "last_episode_at": part["episode_start"].max().isoformat(),
                "median_duration_minutes": round(float(part["duration"].median()), 1),
            }
    return history


def incident_probabilities(predictions):
    path = os.path.join(artifacts.artifact_dir(INCIDENT_MODEL), "incident_calibrator.joblib")
    if not os.path.exists(path):
        return []
    import joblib

    calibrator = joblib.load(path)
    locations = {}
    for row in predictions:
        group = location_group(row.get("tag"))
        if row["model_id"] != INCIDENT_MODEL or group is None:
            continue
        best = locations.setdefault(group, {"raw": row["raw_score"], "channels": 0})
        best["raw"] = max(best["raw"], row["raw_score"])
        best["channels"] += 1
    return [
        {
            "location_group": group,
            "scenario": SCENARIOS["phase"],
            "model_id": INCIDENT_MODEL,
            "horizon_hours": 24,
            "probability": round(calibrated(calibrator, item["raw"]), 4),
            "channels": item["channels"],
        }
        for group, item in locations.items()
    ]


def assess_alarms(reference, until):
    from pipeline.targets import modules

    model, meta = artifacts.load_artifact(ALARM_MODEL)
    calibrator = artifacts.load_calibrator(ALARM_MODEL)
    frame = modules.build_alarm_frame(include_lockbox=True)
    recent = frame.loc[frame["ts"] > until - pd.Timedelta(days=RECENT_DAYS)].reset_index(drop=True)
    raw = model.predict_proba(recent[meta["feature_columns"]])
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), *PROBABILITY_RANGE)
    threshold = meta["model_config"]["isolated_threshold"]
    rows = []
    for item, score, prob in zip(recent.itertuples(), raw, probability, strict=True):
        info = reference.get(str(item.channel_id), {})
        rows.append({
            "channel_id": str(item.channel_id),
            "ts": item.ts.isoformat(),
            "sensor_type": item.sensor_type,
            "corroboration_probability": round(float(prob), 4),
            "needs_verification": bool(score < threshold) and not bool(item.maintenance),
            "maintenance": bool(item.maintenance),
            "tag": info.get("tag"),
            "name": info.get("name"),
        })
    return rows


def _armed_triggers(reference):
    from pipeline import extract

    tag_by_channel = {key: value.get("tag") for key, value in reference.items()}
    guard = access.guard_states(extract.extract_events(access.GUARD_SENSOR), tag_by_channel)
    triggers = pd.concat(
        [access.triggers(extract.extract_events(sensor), sensor, tag_by_channel) for sensor in access.ACCESS_SENSORS],
        ignore_index=True,
    )
    return access.assess(triggers, guard)


def assess_access(reference, until):
    with open(ACCESS_CONFIG, encoding="utf-8") as handle:
        threshold = json.load(handle)["flag_threshold"]
    scored = _armed_triggers(reference)
    recent = scored.loc[(scored["ts"] > until - pd.Timedelta(days=RECENT_DAYS)) & (scored["index"] >= threshold)]
    return [
        {
            "channel_id": item.channel_id,
            "ts": item.ts.isoformat(),
            "sensor_type": item.sensor_type,
            "object": item.object,
            "access_index": round(float(item.index), 4),
            "night": bool(item.night),
            "chain": bool(item.chain),
            "tag": reference.get(item.channel_id, {}).get("tag"),
            "name": reference.get(item.channel_id, {}).get("name"),
        }
        for item in recent.itertuples()
    ]


def forecast_weather():
    from pipeline import weather

    try:
        return weather.fetch_forecast()
    except Exception as error:  # noqa: BLE001
        print(f"weather forecast unavailable: {error}")
        return None


def assess_routes(reference, until):
    scored = _armed_triggers(reference)
    recent = scored.loc[scored["ts"] > until - pd.Timedelta(days=RECENT_DAYS)]
    names = {key: value.get("name") for key, value in reference.items()}
    result = access.routes(recent, names)
    for route in result:
        route["start"], route["end"] = route["start"].isoformat(), route["end"].isoformat()
        for step in route["steps"]:
            step["ts"] = step["ts"].isoformat()
    return result


def write_snapshot(
    predictions, prediction_time, output, alarms=None, access_events=None, incidents=None, stream=None, history=None,
    access_routes=None, weather_forecast=None,
):
    model_info = {}
    for _, names, _ in DEVICES:
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
    if incidents is not None:
        payload["incidents"] = incidents
    if stream is not None:
        payload["stream"] = stream
    if history is not None:
        payload["location_history"] = history
    if alarms is not None:
        payload["alarms"] = alarms
    if access_events is not None:
        payload["access_events"] = access_events
    if access_routes is not None:
        payload["access_routes"] = access_routes
    if weather_forecast is not None:
        payload["weather_forecast"] = weather_forecast
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
        for device, model_names, target_state in DEVICES:
            if device not in DEMO_CHANNELS:
                continue
            device_ids = {channel_id for channel_id, _ in DEMO_CHANNELS[device]}
            events = demo_events[demo_events["channel_id"].isin(device_ids)]
            predictions.extend(score_rows(device, model_names, target_state, events, {}))
        write_snapshot(predictions, prediction_time, arguments.output)
        return

    from pipeline import extract

    reference = channel_reference()
    prediction_time = None
    predictions = []
    for device, _, _ in DEVICES:
        events = extract.extract_events(sensor_of(device))
        device_time = events["ts"].max()
        prediction_time = device_time if prediction_time is None else max(prediction_time, device_time)

    for device, model_names, target_state in DEVICES:
        predictions.extend(
            score_device(device, model_names, target_state, arguments.limit, reference)
        )

    until = pd.Timestamp(prediction_time)
    write_snapshot(
        predictions,
        prediction_time,
        arguments.output,
        alarms=assess_alarms(reference, until),
        access_events=assess_access(reference, until),
        access_routes=assess_routes(reference, until),
        weather_forecast=forecast_weather(),
        incidents=incident_probabilities(predictions),
        history=location_history(
            {sensor_of(device): extract.extract_events(sensor_of(device)) for device, _, _ in DEVICES}, reference, until
        ),
    )


if __name__ == "__main__":
    main()
