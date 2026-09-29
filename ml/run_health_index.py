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


def scored(name, frame, episodes, year=YEAR):
    meta = artifacts.load_artifact(name)[1]
    model, calibrator = recipes.out_of_sample(name, frame, year)
    part = frame.loc[frame["ts"].dt.year == year].reset_index(drop=True)
    raw = model.predict_proba(part[meta["feature_columns"]])
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1)
    forecasts = part[["channel_id", "ts"]].assign(probability=probability, model=name)
    forecasts["channel_id"] = forecasts["channel_id"].astype(str)
    starts = episodes[["channel_id", "episode_start"]].assign(channel_id=lambda e: e["channel_id"].astype(str))
    return forecasts, starts.loc[starts["episode_start"].dt.year == year]


def daily_cuts(year=YEAR, reuse=False):
    cache = os.path.join(config.ROOT, "analysis", "ml_ready", "cache", f"health_daily_{year}.parquet")
    if reuse and os.path.exists(cache):
        return pd.read_parquet(cache)
    lockbox = year > 2025
    forecasts, starts = [], []
    for device in ("pump", "fan", "smoke"):
        ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        f, s = scored(f"{device}_24h", ctx.build(horizon_hours=24), ctx.episodes, year)
        forecasts.append(f)
        starts.append(s)
        log(f"{device}: {len(f)} forecasts")
    phase_events = extract.extract_events(modules.PHASE_SENSOR)
    frame, episodes, _ = modules.build_phase_frame(phase_events, horizons=(24,), include_lockbox=lockbox)
    f, s = scored("phase_24h", frame.rename(columns={"any_y24": "target"}), episodes, year)
    forecasts.append(f)
    starts.append(s)
    if os.path.exists(os.path.join(artifacts.artifact_dir("smoke_alarm_24h"), "meta.json")):
        smoke_events = extract.extract_events(config.SENSOR_ALIASES["smoke"])
        frame, episodes = state_target.build_frame(smoke_events, "Обнаружен дым", horizons=(24,), include_lockbox=lockbox)
        f, s = scored("smoke_alarm_24h", frame.rename(columns={"y24": "target"}), episodes, year)
        forecasts.append(f)
        starts.append(s)
    pump_events = extract.extract_events(config.SENSOR_ALIASES["pump"])
    frame, episodes, _ = flood.build_frame(pump_events, weather_mod.fetch_weather(), 24)
    f, s = scored("flood_24h", frame, episodes, year)
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
    last = min(forecasts["ts"].max().normalize(), pd.Timestamp(f"{year}-12-31"))
    for day in pd.date_range(f"{year}-01-02", last, freq="D"):
        window = forecasts.loc[(forecasts["ts"] >= day - HORIZON) & (forecasts["ts"] < day)]
        if window.empty:
            continue
        latest = window.groupby(["model", "channel_id"]).tail(1)
        risk = latest.groupby(["group", "scenario"])["probability"].max()
        raw = 1 - (1 - risk).groupby(level="group").prod()
        future = set(starts.loc[(starts["episode_start"] >= day) & (starts["episode_start"] < day + HORIZON), "group"])
        rows.append(pd.DataFrame({"group": raw.index, "raw": raw.values, "event": raw.index.isin(future), "day": day}))
        if day.day == 1:
            log(f"{day:%Y-%m}")
    daily = pd.concat(rows, ignore_index=True)
    daily.to_parquet(cache)
    return daily


def quality(event, risk):
    return {
        "ece": round(float(calibration.expected_calibration_error(event, risk)[0]), 4),
        "roc_auc": round(float(roc_auc_score(event, risk)), 4),
        "pr_auc": round(float(average_precision_score(event, risk)), 4),
    }


def main() -> None:
    train, test = daily_cuts(YEAR), daily_cuts(YEAR + 1)
    x, y = train["raw"].to_numpy(), train["event"].to_numpy().astype(int)
    tx, ty = test["raw"].to_numpy(), test["event"].to_numpy().astype(int)
    isotonic = np.clip(calibration.apply_isotonic(calibration.fit_isotonic(x, y), tx), 0, 1)
    risk = calibration.apply_points(calibration.fit_smooth_isotonic(x, y), tx)
    raw_final, risk_final = calibration.fit_smooth_isotonic(np.concatenate([x, tx]), np.concatenate([y, ty]))
    with open(CALIBRATION, "w", encoding="utf-8") as handle:
        json.dump({
            "raw_risk": [round(float(value), 6) for value in raw_final],
            "risk": [round(float(value), 6) for value in risk_final],
            "basis": f"daily location cuts of {YEAR} and {YEAR + 1}H1, isotonic on 40 logit bins smoothed with PCHIP",
        }, handle, indent=1)
    index = 100 * (1 - risk)
    report = {
        "method": "isotonic on 40 logit bins smoothed with PCHIP, fitted on 2025, checked on 2026H1",
        "ece_raw": quality(ty, tx)["ece"],
        "ece_calibrated": quality(ty, risk)["ece"],
        "period": f"{YEAR + 1}H1",
        "location_days": int(len(test)),
        "locations": int(test["group"].nunique()),
        "event_rate": round(float(ty.mean()), 4),
        "roc_auc": quality(ty, risk)["roc_auc"],
        "pr_auc": quality(ty, risk)["pr_auc"],
        "compared": {"raw": quality(ty, tx), "isotonic": quality(ty, isotonic), "smooth_isotonic": quality(ty, risk)},
        "bands": [
            {
                "index": f"{low}-{min(high, 100)}",
                "location_days": int(mask.sum()),
                "event_rate": round(float(ty[mask].mean()), 4) if mask.any() else None,
                "predicted_risk": round(float(risk[mask].mean()), 4) if mask.any() else None,
            }
            for low, high in BANDS
            for mask in [(index >= low) & (index < high)]
        ],
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
