import json
import os
import sys
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, config, context, episodes as episodes_mod, evaluate, experiments, extract, recipes, splits
from pipeline.formal import metrics as fm
from pipeline.targets import modules
from run_isolated_faults import power_times, split_episodes
from run_refit_study import EMBARGO, current_window, training_rows

OUTPUT = os.path.join(os.path.dirname(__file__), "power_cascade.json")
PHASE_RECIPE = "catboost"
PHASE_WINDOW_YEARS = 3


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5,))
    return {"base_rate": round(float(np.mean(target)), 4), "avg_precision": round(float(frontier["pr_auc"]), 4),
            "roc_auc": round(float(frontier["roc_auc"]), 4), "top5_per_day": top["precision_top5_per_day"]}


def out_of_fold_power(object_of):
    events = extract.extract_events(modules.PHASE_SENSOR)
    frame = modules.build_phase_frame(events, horizons=(24,), include_lockbox=True)[0].rename(columns={"any_y24": "target"})
    columns = artifacts.load_artifact("phase_24h")[1]["feature_columns"]
    parts = []
    for year in range(2021, 2027):
        train = (frame["ts"] < pd.Timestamp(f"{year}-01-01") - EMBARGO) & (frame["ts"].dt.year >= year - PHASE_WINDOW_YEARS)
        score = frame["ts"].dt.year == year
        model = recipes.fit(PHASE_RECIPE, frame.loc[train, columns], frame.loc[train, "target"])
        parts.append(frame.loc[score, ["channel_id", "ts"]].assign(score=model.predict_proba(frame.loc[score, columns])))
        log(f"phase scores for {year}: {int(score.sum())}")
    scores = pd.concat(parts, ignore_index=True)
    scores["object"] = scores["channel_id"].astype(str).map(object_of)
    scores["hour"] = scores["ts"].dt.floor("h")
    hourly = scores.dropna(subset=["object"]).groupby(["object", "hour"])["score"].agg(["max", "mean", "size"]).reset_index()
    rolled = []
    for key, group in hourly.groupby("object"):
        series = group.set_index("hour").sort_index()
        window = series.rolling("24h")
        rolled.append(pd.DataFrame({"object": key, "hour": series.index,
                                    "power_risk_max_24h": window["max"].max().to_numpy(),
                                    "power_risk_mean_24h": window["mean"].mean().to_numpy(),
                                    "power_scores_24h": window["size"].sum().to_numpy()}))
    return pd.concat(rolled, ignore_index=True)


def attach(frame, power, object_of):
    keys = frame[["channel_id", "ts"]].copy()
    keys["object"] = keys["channel_id"].astype(str).map(object_of)
    keys["hour"] = keys["ts"].dt.floor("h") - pd.Timedelta(hours=1)
    keys["_row"] = np.arange(len(keys))
    keys = keys.sort_values("hour")
    merged = pd.merge_asof(keys.dropna(subset=["object"]), power.sort_values("hour"), on="hour", by="object",
                           direction="backward", tolerance=pd.Timedelta(hours=24))
    out = pd.DataFrame(index=range(len(frame)), columns=["power_risk_max_24h", "power_risk_mean_24h", "power_scores_24h"], dtype=float)
    out.loc[merged["_row"].to_numpy(), :] = merged[out.columns].to_numpy()
    out.index = frame.index
    return out


def main() -> None:
    names = sys.argv[1:] or ["pump_24h", "pump_72h", "fan_24h", "fan_72h"]
    object_of, _ = context.locations()
    power = out_of_fold_power(object_of)
    times = power_times(object_of)
    report, ctx = {}, None
    for name in names:
        device, horizon = name.split("_")[0], int(name.split("_")[1][:-1])
        if ctx is None or ctx.sensor_type != config.SENSOR_ALIASES[device]:
            ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        _, coincident = split_episodes(ctx.episodes, object_of, times)
        meta = artifacts.load_artifact(name)[1]
        base, recipe, window = meta["feature_columns"], recipes.recipe_of(meta), current_window(meta)
        frame = splits.assign_split(episodes_mod.assign_targets(ctx.features_base, ctx.episodes, horizon)).reset_index(drop=True)
        frame["target_coincident"] = episodes_mod.assign_targets(frame[["channel_id", "ts"]], coincident, horizon)["target"].to_numpy()
        extra = attach(frame, power, object_of)
        frame = pd.concat([frame, extra], axis=1)
        year = frame["ts"].dt.year
        result = {"recipe": recipe, "window": window}
        for period, before, test in (("2025", 2025, (year == 2025).to_numpy()),
                                     ("2026H1", 2026, ((year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon))).to_numpy())):
            train = training_rows(frame, before, window).to_numpy()
            ts = frame.loc[test, "ts"].to_numpy()
            for label, columns in (("base", base), ("cascade", base + list(extra.columns))):
                model = recipes.fit(recipe, frame.loc[train, columns], frame.loc[train, "target"])
                score = model.predict_proba(frame.loc[test, columns])
                result[f"{period}_{label}"] = summary(frame.loc[test, "target"].to_numpy(), score, ts)
                result[f"{period}_{label}_on_coincident"] = summary(frame.loc[test, "target_coincident"].to_numpy(), score, ts)
                log(f"{name} {period} {label}: {result[f'{period}_{label}']} coincident {result[f'{period}_{label}_on_coincident']}")
        report[name] = result
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
