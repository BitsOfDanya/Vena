import argparse
import json
import os
import time

import joblib
import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, extract, recipes, training
from pipeline.formal import metrics as fm
from pipeline.targets import state_target
from run_refit_study import MIN_GAIN, RECENT_YEAR, SELECTION_YEAR, WINDOWS, quality, training_rows

NAME = "smoke_alarm_24h"
SENSOR = config.SENSOR_ALIASES["smoke"]
STATE = "Обнаружен дым"
HORIZON = 24
PRIOR = "channel_failure_prior"
RISK_PERCENTILES = {"critical": 0.001, "high": 0.005, "medium": 0.02}
OUTPUT = os.path.join(config.ROOT, "results", "detection_study.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true", help=f"save the refit as {NAME}")
    args = parser.parse_args()

    events = extract.extract_events(SENSOR)
    frame, episodes = state_target.build_frame(events, STATE, horizons=(HORIZON,), include_lockbox=True)
    frame = frame.rename(columns={f"y{HORIZON}": "target"}).reset_index(drop=True)
    rates = state_target.global_rates(events, STATE, config.TRAIN_YEARS[1])
    columns = training.feature_columns()
    year = frame["ts"].dt.year
    select = (year == SELECTION_YEAR).values
    recent = ((year == RECENT_YEAR) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=HORIZON))).values
    target = frame["target"].values
    log(f"{len(frame)} candidates, {len(episodes)} episodes, selection {int(select.sum())}, recent {int(recent.sum())}")

    candidates, fitted = [], {}
    for window in WINDOWS:
        rows = training_rows(frame, SELECTION_YEAR, window).values
        for recipe in recipes.RECIPES:
            model = recipes.fit(recipe, frame.loc[rows, columns], target[rows])
            score = model.predict_proba(frame.loc[select, columns])
            ap = float(fm.frontier_metrics(target[select], score)["pr_auc"])
            candidates.append({"recipe": recipe, "window": window, "avg_precision_2025": round(ap, 4)})
            fitted[(recipe, window)] = (model, score)
            log(f"{recipe}/{window} AP 2025 {ap:.4f}")
    best = max(candidates, key=lambda row: row["avg_precision_2025"])
    staging, staging_score = fitted[(best["recipe"], best["window"])]
    calibrator = calibration.fit_isotonic(staging_score, target[select])

    rows = training_rows(frame, RECENT_YEAR, best["window"]).values
    refit = recipes.fit(best["recipe"], frame.loc[rows, columns], target[rows])
    recent_target, recent_ts = target[recent], frame.loc[recent, "ts"].values
    raw = refit.predict_proba(frame.loc[recent, columns])
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0, 1)
    prior = frame.loc[recent, PRIOR].fillna(0).values
    report = {
        "target": f"start of a '{STATE}' episode within {HORIZON} h",
        "channels": int(frame["channel_id"].nunique()),
        "episodes": int(len(episodes)),
        "recent": {"period": f"{RECENT_YEAR}H1", "n": int(recent.sum()), "base_rate": round(float(recent_target.mean()), 4)},
        "channel_prior": quality(recent_target, prior, None, recent_ts),
        "refit": {"recipe": best["recipe"], "window": best["window"], "train_years": f"through {RECENT_YEAR - 1}",
                  **quality(recent_target, raw, probability, recent_ts)},
        "candidates_2025": candidates,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps({key: report[key] for key in ("recent", "channel_prior", "refit")}, ensure_ascii=False))

    if not args.freeze:
        return
    if report["refit"]["avg_precision"] <= report["channel_prior"]["avg_precision"] + MIN_GAIN:
        log("the model does not beat the channel's own detection rate, nothing frozen")
        return
    window = WINDOWS[best["window"]]
    first_year = RECENT_YEAR - window if window else config.TRAIN_YEARS[0]
    model_config = {
        "model_name": best["recipe"],
        "recipe": best["recipe"],
        "horizon_hours": HORIZON,
        "target_state": STATE,
        "numeric_mode": False,
        "duty_cycle_mode": False,
        "with_neighbors": False,
        "global_rates": rates,
        "calibrated": True,
        "risk_level_thresholds": {level: float(np.quantile(raw, 1 - share)) for level, share in RISK_PERCENTILES.items()},
        "calibration": {"method": "isotonic", "fit_period": f"{SELECTION_YEAR}, same recipe trained through {SELECTION_YEAR - 1}",
                        "evaluated_on": f"{RECENT_YEAR}H1", "ece_calibrated": report["refit"]["ece"]},
    }
    period = {"train_years": f"{first_year}-{RECENT_YEAR - 1}"}
    artifacts.save_artifact(NAME, refit, columns, model_config, period,
                            {"test": {"period": f"{RECENT_YEAR}H1", **report["refit"]}, "channel_prior": report["channel_prior"]},
                            version=time.strftime("%Y-%m-%d"))
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(NAME), "calibrator.joblib"))
    with open(os.path.join(config.ROOT, "configs", "models", f"{NAME}.json"), "w", encoding="utf-8") as handle:
        json.dump({"sensor_type": SENSOR, "tag": "smoke_alarm", "model": model_config, "feature_columns": columns,
                   "artifact": NAME, "training_period": period}, handle, indent=2, ensure_ascii=False)
    log(f"{NAME} frozen")


if __name__ == "__main__":
    main()
