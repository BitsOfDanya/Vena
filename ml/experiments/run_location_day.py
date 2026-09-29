import json
import os
import sys
import time

import pandas as pd

from pipeline import artifacts, context, evaluate
from pipeline.formal import metrics as fm
from run_refit_study import frames

OUTPUT = os.path.join(os.path.dirname(__file__), "location_day.json")
LEVELS = ("channel", "section", "object")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def daily(scored, starts, key, horizon):
    rows = []
    for day in pd.date_range("2026-01-02", scored["ts"].max().normalize() - pd.Timedelta(hours=horizon), freq="D"):
        window = scored.loc[(scored["ts"] >= day - pd.Timedelta(hours=24)) & (scored["ts"] < day)]
        if window.empty:
            continue
        latest = window.groupby("channel_id").tail(1)
        score = latest.groupby(key)["score"].max()
        future = starts.loc[(starts["episode_start"] >= day) & (starts["episode_start"] < day + pd.Timedelta(hours=horizon)), key]
        rows.append(pd.DataFrame({"key": score.index, "score": score.values, "day": day,
                                  "target": score.index.isin(set(future)).astype(int)}))
    return pd.concat(rows, ignore_index=True)


def summary(frame):
    frontier = fm.frontier_metrics(frame["target"].to_numpy(), frame["score"].to_numpy())
    top = evaluate.evaluate_daily_topk_fixed(frame["day"].to_numpy(), frame["target"].to_numpy(), frame["score"].to_numpy(), counts=(3, 5, 10))
    return {"units_per_day": round(len(frame) / frame["day"].nunique(), 1), "base_rate": round(float(frame["target"].mean()), 4),
            "avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            **{f"top{k}_per_day": top[f"precision_top{k}_per_day"] for k in (3, 5, 10)}}


def main() -> None:
    names = sys.argv[1:] or ["pump_72h", "fan_72h", "flood_24h", "phase_24h", "smoke_24h"]
    object_of, section_of = context.locations()
    report = {}
    for name, frame, horizon in frames(names):
        model, meta = artifacts.load_artifact(name)
        recent = frame.loc[frame["ts"].dt.year == 2026, ["channel_id", "ts", *meta["feature_columns"]]].copy()
        recent["channel_id"] = recent["channel_id"].astype(str)
        scored = recent[["channel_id", "ts"]].assign(score=model.predict_proba(recent[meta["feature_columns"]])).sort_values("ts")
        scored["channel"] = scored["channel_id"]
        scored["section"] = scored["channel_id"].map(section_of)
        scored["object"] = scored["channel_id"].map(object_of)
        starts = starts_of(name, section_of, object_of)
        report[name] = {}
        for level in LEVELS:
            report[name][level] = summary(daily(scored.dropna(subset=[level]), starts.dropna(subset=[level]), level, horizon))
            log(f"{name} {level}: {report[name][level]}")
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)


def starts_of(name, section_of, object_of):
    from pipeline import config, episodes as episodes_mod, extract
    from pipeline.targets import discovery, flood, modules

    if name.startswith(("pump", "fan", "smoke")):
        episodes = episodes_mod.build_episodes(extract.extract_events(config.SENSOR_ALIASES[name.split("_")[0]]))
    elif name == "flood_24h":
        episodes = discovery.state_episodes(extract.extract_events(config.SENSOR_ALIASES["pump"]), flood.FLOOD_STATE)
    else:
        episodes = discovery.state_episodes(extract.extract_events(modules.PHASE_SENSOR), modules.PHASE_STATE)
    starts = episodes[["channel_id", "episode_start"]].copy()
    starts["channel_id"] = starts["channel_id"].astype(str)
    starts["channel"] = starts["channel_id"]
    starts["section"] = starts["channel_id"].map(section_of)
    starts["object"] = starts["channel_id"].map(object_of)
    return starts


if __name__ == "__main__":
    main()
