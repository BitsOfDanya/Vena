import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, context, experiments, extract, weather as weather_mod
from pipeline.locations import location_group
from pipeline.targets import flood, modules, state_target
from run_health_index import SCENARIO

START = pd.Timestamp("2026-01-01")
OUTPUT = os.path.join(config.ROOT, "results", "health_history.json")
CALIBRATION = os.path.join(config.ROOT, "configs", "health_index.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def scored(name, frame):
    model, meta = artifacts.load_artifact(name)
    calibrator = artifacts.load_calibrator(name)
    part = frame.loc[frame["ts"] >= START - pd.Timedelta(days=1)].reset_index(drop=True)
    raw = model.predict_proba(part[meta["feature_columns"]])
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1) if calibrator is not None else raw
    return part[["channel_id", "ts"]].assign(probability=probability, model=name, channel_id=part["channel_id"].astype(str))


def forecasts():
    parts = []
    for device in ("pump", "fan", "smoke"):
        ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        parts.append(scored(f"{device}_24h", ctx.build(horizon_hours=24)))
        log(f"{device}: scored")
    phase = extract.extract_events(modules.PHASE_SENSOR)
    frame = modules.build_phase_frame(phase, horizons=(24,), include_lockbox=True)[0]
    parts.append(scored("phase_24h", frame))
    pump = extract.extract_events(config.SENSOR_ALIASES["pump"])
    parts.append(scored("flood_24h", flood.build_frame(pump, weather_mod.fetch_weather(), 24)[0]))
    if os.path.exists(os.path.join(artifacts.artifact_dir("smoke_alarm_24h"), "meta.json")):
        smoke = extract.extract_events(config.SENSOR_ALIASES["smoke"])
        parts.append(scored("smoke_alarm_24h", state_target.build_frame(smoke, "Обнаружен дым", horizons=(24,), include_lockbox=True)[0]))
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    with open(CALIBRATION, encoding="utf-8") as handle:
        points = json.load(handle)
    dictionary = extract.channel_dictionary()
    groups = {str(k): location_group(v) for k, v in zip(dictionary.iloc[:, 0], dictionary.iloc[:, 3], strict=True)}
    object_of, _ = context.locations()
    group_object = {}
    for channel, group in groups.items():
        if group and object_of.get(channel):
            group_object.setdefault(group, object_of[channel])
    data = forecasts()
    data["group"] = data["channel_id"].map(groups)
    data["scenario"] = data["model"].map(SCENARIO)
    data = data.dropna(subset=["group"]).sort_values("ts")
    sections, objects = {}, {}
    xs = np.asarray(points["raw_risk"], dtype=float)
    ys = np.asarray(points["risk"], dtype=float)
    for day in pd.date_range(START, data["ts"].max().normalize(), freq="D"):
        window = data.loc[(data["ts"] >= day - pd.Timedelta(hours=24)) & (data["ts"] < day)]
        if window.empty:
            continue
        latest = window.groupby(["model", "channel_id"]).tail(1)
        risk = latest.groupby(["group", "scenario"])["probability"].max()
        raw_series = 1 - (1 - risk).groupby(level="group").prod()
        raw = raw_series.to_numpy(dtype=float)
        index = np.clip(np.rint(100 * (1 - np.interp(raw, xs, ys))), 0, 100).astype(int)
        stamp = day.date().isoformat()
        for group, value in zip(raw_series.index, index, strict=True):
            sections.setdefault(group, []).append([stamp, int(value)])
            key = group_object.get(group)
            if key:
                current = objects.setdefault(key, {})
                current[stamp] = min(current.get(stamp, 100), int(value))
    report = {
        "period": f"{START.date()} — {data['ts'].max().date()}",
        "basis": "production models, each channel's latest 24-hour probability before midnight",
        "objects": {key: sorted(days.items()) for key, days in objects.items()},
        "sections": sections,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, separators=(",", ":"))
    log(f"{len(objects)} objects, {len(sections)} sections -> {OUTPUT}")


if __name__ == "__main__":
    main()
