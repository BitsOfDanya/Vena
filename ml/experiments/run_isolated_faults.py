import json
import os
import sys
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, config, context, episodes as episodes_mod, evaluate, experiments, extract, recipes, splits
from pipeline.formal import metrics as fm
from pipeline.targets import modules
from run_refit_study import current_window, training_rows

OUTPUT = os.path.join(os.path.dirname(__file__), "isolated_faults.json")
COINCIDENCE = np.timedelta64(2, "m")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5,))
    return {"base_rate": round(float(np.mean(target)), 4), "avg_precision": round(float(frontier["pr_auc"]), 4),
            "roc_auc": round(float(frontier["roc_auc"]), 4), "top5_per_day": top["precision_top5_per_day"]}


def power_times(object_of):
    phase = extract.extract_events(modules.PHASE_SENSOR)
    outages = phase.loc[phase["raw_value"] == modules.PHASE_STATE, ["channel_id", "ts"]]
    keys = outages["channel_id"].astype(str).map(object_of)
    return {key: np.sort(group.to_numpy(dtype="datetime64[ns]")) for key, group in outages.assign(_k=keys).dropna(subset=["_k"]).groupby("_k")["ts"]}


def split_episodes(episodes, object_of, times):
    episodes = episodes.copy()
    episodes["object"] = episodes["channel_id"].astype(str).map(object_of)
    coincident = np.zeros(len(episodes), dtype=bool)
    for key, group in episodes.dropna(subset=["object"]).groupby("object"):
        stamps = times.get(key)
        if stamps is None:
            continue
        start = group["episode_start"].to_numpy(dtype="datetime64[ns]")
        low = np.searchsorted(stamps, start - COINCIDENCE)
        high = np.searchsorted(stamps, start + COINCIDENCE, side="right")
        coincident[episodes.index.get_indexer(group.index)] = high > low
    return episodes.loc[~coincident].drop(columns="object"), episodes.loc[coincident].drop(columns="object")


def main() -> None:
    names = sys.argv[1:] or ["pump_24h", "pump_72h", "fan_24h", "fan_72h"]
    object_of, _ = context.locations()
    times = power_times(object_of)
    report = {}
    contexts = {}
    for name in names:
        device, horizon = name.split("_")[0], int(name.split("_")[1][:-1])
        if device not in contexts:
            contexts = {device: experiments.DeviceContext(config.SENSOR_ALIASES[device])}
        ctx = contexts[device]
        isolated, coincident = split_episodes(ctx.episodes, object_of, times)
        model, meta = artifacts.load_artifact(name)
        columns, recipe, window = meta["feature_columns"], recipes.recipe_of(meta), current_window(meta)
        frame = splits.assign_split(episodes_mod.assign_targets(ctx.features_base, isolated, horizon)).reset_index(drop=True)
        frame["target_all"] = episodes_mod.assign_targets(ctx.features_base[["channel_id", "ts"]], ctx.episodes, horizon)["target"].to_numpy()
        frame["target_coincident"] = episodes_mod.assign_targets(ctx.features_base[["channel_id", "ts"]], coincident, horizon)["target"].to_numpy()
        year = frame["ts"].dt.year
        recent = ((year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon))).to_numpy()
        ts = frame.loc[recent, "ts"].to_numpy()
        production = model.predict_proba(frame.loc[recent, columns])
        result = {"episodes": int(len(ctx.episodes)), "isolated_share": round(len(isolated) / len(ctx.episodes), 4),
                  "production_on_all": summary(frame.loc[recent, "target_all"].to_numpy(), production, ts),
                  "production_on_coincident": summary(frame.loc[recent, "target_coincident"].to_numpy(), production, ts),
                  "production_on_isolated": summary(frame.loc[recent, "target"].to_numpy(), production, ts)}
        for period, before, test in (("2025", 2025, (year == 2025).to_numpy()), ("2026H1", 2026, recent)):
            train = training_rows(frame, before, window).to_numpy()
            y = frame.loc[test, "target"].to_numpy()
            for candidate in dict.fromkeys((recipe, "catboost", "lightgbm")):
                fitted = recipes.fit(candidate, frame.loc[train, columns], frame.loc[train, "target"])
                result[f"isolated_{period}_{candidate}"] = summary(y, fitted.predict_proba(frame.loc[test, columns]), frame.loc[test, "ts"].to_numpy())
                log(f"{name} {period} {candidate}: {result[f'isolated_{period}_{candidate}']}")
        log(f"{name}: {json.dumps({k: v for k, v in result.items() if k.startswith('production') or k.endswith('share')})}")
        report[name] = result
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
