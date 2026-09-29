"""Validate the location health index on daily cuts of 2025.

The API computes a location's health index from the 24-hour forecasts: for each
scenario the highest calibrated probability among the location's channels,
combined as 100 * prod(1 - risk). At every midnight of 2025 this script takes
each channel's latest forecast from the previous 24 hours, computes the index
per location and checks whether any modelled event (fault, power loss,
flooding, smoke detection) started at the location within the next 24 hours. The report gives
the event rate by index band and the ranking quality of the index.

Combining channel probabilities overstates the risk of large, busy locations,
so the raw location risk is calibrated on these daily cuts (isotonic, checked by
two-fold cross-fitting over alternate months). The calibration points go to
configs/health_index.json, which the API interpolates:
index = 100 * (1 - calibrated risk).
"""

import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from pipeline import artifacts, calibration, config, experiments, extract, recipes, weather as weather_mod
from pipeline.locations import location_group
from pipeline.targets import flood, modules, state_target

YEAR = 2025
HORIZON = pd.Timedelta(hours=24)
BANDS = [(0, 25), (25, 50), (50, 75), (75, 90), (90, 101)]
SCENARIO = {"pump_24h": "flooding", "fan_24h": "ventilation", "smoke_24h": "fire", "phase_24h": "power_loss",
            "flood_24h": "flooding", "smoke_alarm_24h": "fire"}
OUTPUT = os.path.join(config.ROOT, "results", "health_index.json")
CALIBRATION = os.path.join(config.ROOT, "configs", "health_index.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def scored(name, frame, episodes):
    meta = artifacts.load_artifact(name)[1]
    model, calibrator = recipes.out_of_sample(name, frame, YEAR)
    part = frame.loc[frame["ts"].dt.year == YEAR].reset_index(drop=True)
    raw = model.predict_proba(part[meta["feature_columns"]])
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1)
    forecasts = part[["channel_id", "ts"]].assign(probability=probability, model=name)
    forecasts["channel_id"] = forecasts["channel_id"].astype(str)
    starts = episodes[["channel_id", "episode_start"]].assign(channel_id=lambda e: e["channel_id"].astype(str))
    return forecasts, starts.loc[starts["episode_start"].dt.year == YEAR]


def main() -> None:
    forecasts, starts = [], []
    for device in ("pump", "fan", "smoke"):
        ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        f, s = scored(f"{device}_24h", ctx.build(horizon_hours=24), ctx.episodes)
        forecasts.append(f)
        starts.append(s)
        log(f"{device}: {len(f)} forecasts")
    phase_events = extract.extract_events(modules.PHASE_SENSOR)
    frame, episodes, _ = modules.build_phase_frame(phase_events, horizons=(24,))
    f, s = scored("phase_24h", frame.rename(columns={"any_y24": "target"}), episodes)
    forecasts.append(f)
    starts.append(s)
    if os.path.exists(os.path.join(artifacts.artifact_dir("smoke_alarm_24h"), "meta.json")):
        smoke_events = extract.extract_events(config.SENSOR_ALIASES["smoke"])
        frame, episodes = state_target.build_frame(smoke_events, "Обнаружен дым", horizons=(24,))
        f, s = scored("smoke_alarm_24h", frame.rename(columns={"y24": "target"}), episodes)
        forecasts.append(f)
        starts.append(s)
    pump_events = extract.extract_events(config.SENSOR_ALIASES["pump"])
    frame, episodes, _ = flood.build_frame(pump_events, weather_mod.fetch_weather(), 24)
    f, s = scored("flood_24h", frame, episodes)
    forecasts.append(f)
    starts.append(s)

    dictionary = extract.channel_dictionary()
    groups = {str(k): location_group(v) for k, v in zip(dictionary.iloc[:, 0], dictionary.iloc[:, 3], strict=True)}
    forecasts = pd.concat(forecasts, ignore_index=True)
    forecasts["group"] = forecasts["channel_id"].map(groups)
    forecasts["scenario"] = forecasts["model"].map(SCENARIO)
    forecasts = forecasts.dropna(subset=["group"]).sort_values("ts")
    starts = pd.concat(starts, ignore_index=True)
    starts["group"] = starts["channel_id"].map(groups)
    starts = starts.dropna(subset=["group"])

    rows = []
    for day in pd.date_range(f"{YEAR}-01-02", f"{YEAR}-12-31", freq="D"):
        window = forecasts.loc[(forecasts["ts"] >= day - HORIZON) & (forecasts["ts"] < day)]
        if window.empty:
            continue
        latest = window.groupby(["model", "channel_id"]).tail(1)
        risk = latest.groupby(["group", "scenario"])["probability"].max()
        health = (1 - risk).groupby(level="group").prod() * 100
        future = set(starts.loc[(starts["episode_start"] >= day) & (starts["episode_start"] < day + HORIZON), "group"])
        rows.append(pd.DataFrame({"group": health.index, "index": health.values, "event": health.index.isin(future), "day": day}))
        if day.day == 1:
            log(f"{day:%Y-%m}")
    daily = pd.concat(rows, ignore_index=True)
    raw = (1 - daily["index"] / 100).to_numpy()
    event = daily["event"].to_numpy().astype(int)
    fold = (daily["day"].dt.month % 2).to_numpy()
    cross = np.zeros(len(raw))
    for part in (0, 1):
        fitted = calibration.fit_isotonic(raw[fold != part], event[fold != part])
        cross[fold == part] = np.clip(calibration.apply_isotonic(fitted, raw[fold == part]), 0, 1)
    final = calibration.fit_isotonic(raw, event)
    with open(CALIBRATION, "w", encoding="utf-8") as handle:
        json.dump({
            "raw_risk": [round(float(x), 6) for x in final.X_thresholds_],
            "risk": [round(float(y), 6) for y in final.y_thresholds_],
            "basis": f"daily location cuts of {YEAR}, isotonic",
        }, handle, indent=1)
    daily["index"] = 100 * (1 - cross)
    risk = pd.Series(cross)
    report = {
        "ece_raw": round(float(calibration.expected_calibration_error(event, raw)[0]), 4),
        "ece_calibrated": round(float(calibration.expected_calibration_error(event, cross)[0]), 4),
        "period": str(YEAR),
        "location_days": int(len(daily)),
        "locations": int(daily["group"].nunique()),
        "event_rate": round(float(daily["event"].mean()), 4),
        "roc_auc": round(float(roc_auc_score(daily["event"], risk)), 4),
        "pr_auc": round(float(average_precision_score(daily["event"], risk)), 4),
        "bands": [
            {
                "index": f"{low}-{min(high, 100)}",
                "location_days": int(mask.sum()),
                "event_rate": round(float(daily.loc[mask, "event"].mean()), 4) if mask.any() else None,
                "predicted_risk": round(float(risk[mask].mean()), 4) if mask.any() else None,
            }
            for low, high in BANDS
            for mask in [(daily["index"] >= low) & (daily["index"] < high)]
        ],
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
