import json
import os
import time

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from pipeline import artifacts, calibration, config, extract, recipes
from pipeline.locations import location_group
from pipeline.targets import modules

NAME = "phase_24h"
YEAR = 2025
HORIZON = pd.Timedelta(hours=24)
OUTPUT = os.path.join(config.ROOT, "results", "incident_calibration.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def daily_locations(scored, starts, groups):
    scored = scored.assign(group=scored["channel_id"].map(groups)).dropna(subset=["group"])
    scored = scored.sort_values("ts")
    starts = starts.assign(group=starts["channel_id"].map(groups)).dropna(subset=["group"])
    rows = []
    for day in pd.date_range(f"{YEAR}-01-02", f"{YEAR}-12-31", freq="D"):
        window = scored.loc[(scored["ts"] >= day - HORIZON) & (scored["ts"] < day)]
        if window.empty:
            continue
        latest = window.groupby("channel_id", observed=True).tail(1)
        location = latest.groupby("group")["score"].agg(["max", "size"])
        future = starts.loc[(starts["episode_start"] >= day) & (starts["episode_start"] < day + HORIZON), "group"]
        location["target"] = location.index.isin(set(future)).astype(int)
        location["day"] = day
        rows.append(location.reset_index())
    return pd.concat(rows, ignore_index=True).rename(columns={"max": "score", "size": "channels"})


def main() -> None:
    meta = artifacts.load_artifact(NAME)[1]
    events = extract.extract_events(modules.PHASE_SENSOR)
    frame, episodes, _ = modules.build_phase_frame(events, horizons=(24,))
    model, _ = recipes.out_of_sample(NAME, frame.rename(columns={"any_y24": "target"}), YEAR)
    valid = frame.loc[frame["ts"].dt.year == YEAR, ["channel_id", "ts"] + meta["feature_columns"]]
    scored = valid[["channel_id", "ts"]].assign(score=model.predict_proba(valid[meta["feature_columns"]]))
    scored["channel_id"] = scored["channel_id"].astype(str)
    episodes = episodes.assign(channel_id=episodes["channel_id"].astype(str))

    dictionary = extract.channel_dictionary()
    groups = {str(k): location_group(v) for k, v in zip(dictionary.iloc[:, 0], dictionary.iloc[:, 3], strict=True)}
    daily = daily_locations(scored, episodes[["channel_id", "episode_start"]], groups)
    log(f"location-days {len(daily)}, locations {daily['group'].nunique()}, base rate {daily['target'].mean():.3f}")

    fold = (daily["day"].dt.month % 2).values
    raw, target = daily["score"].values, daily["target"].values
    cross = np.zeros(len(raw))
    for part in (0, 1):
        fitted = calibration.fit_isotonic(raw[fold != part], target[fold != part])
        cross[fold == part] = np.clip(calibration.apply_isotonic(fitted, raw[fold == part]), 0, 1)
    calibrator = calibration.fit_isotonic(raw, target)
    ece_raw, _ = calibration.expected_calibration_error(target, raw)
    ece_cal, bins = calibration.expected_calibration_error(target, cross)

    report = {
        "model": NAME,
        "period": str(YEAR),
        "location_days": int(len(daily)),
        "locations": int(daily["group"].nunique()),
        "base_rate": round(float(target.mean()), 4),
        "channels_per_location_median": float(daily["channels"].median()),
        "pr_auc": round(float(average_precision_score(target, raw)), 4),
        "roc_auc": round(float(roc_auc_score(target, raw)), 4),
        "ece_raw": round(float(ece_raw), 4),
        "ece_calibrated": round(float(ece_cal), 4),
        "brier_raw": round(float(brier_score_loss(target, raw)), 4),
        "brier_calibrated": round(float(brier_score_loss(target, cross)), 4),
        "reliability": [
            {"n": b["n"], "predicted": round(b["confidence"], 4), "observed": round(b["accuracy"], 4)} for b in bins
        ],
    }
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(NAME), "incident_calibrator.joblib"))
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps({k: v for k, v in report.items() if k != "reliability"}, indent=1))


if __name__ == "__main__":
    main()
