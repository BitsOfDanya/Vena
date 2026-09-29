import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import config, context, episodes as episodes_mod, evaluate, extract, recipes
from pipeline.formal import metrics as fm
from pipeline.targets import discovery, flood, modules

OUTPUT = os.path.join(os.path.dirname(__file__), "station_outage.json")
CLUSTER = pd.Timedelta(minutes=2)
HORIZON = pd.Timedelta(hours=24)
STEP = "6h"
EMBARGO = pd.Timedelta(hours=168)
WINDOWS = {"6h": 6, "1d": 24, "7d": 168, "30d": 720}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(3,))
    return {"base_rate": round(float(np.mean(target)), 4), "avg_precision": round(float(frontier["pr_auc"]), 4),
            "roc_auc": round(float(frontier["roc_auc"]), 4), "recall_at_precision_0.7": round(float(frontier["recall_at_precision_0.7"]), 4),
            "top3_per_day": top["precision_top3_per_day"]}


def clusters(starts, minimum):
    starts = starts.sort_values(["object", "episode_start"])
    gap = starts.groupby("object")["episode_start"].diff()
    starts = starts.assign(cluster=(gap.isna() | (gap > CLUSTER)).cumsum())
    grouped = starts.groupby("cluster").agg(object=("object", "first"), start=("episode_start", "min"), size=("channel_id", "nunique"))
    return grouped.loc[grouped["size"] >= minimum, ["object", "start"]]


def times_by_object(frame, column):
    return {key: np.sort(group.to_numpy(dtype="datetime64[ns]")) for key, group in frame.groupby("object")[column]}


def window_counts(times, moments):
    out = {}
    upto = np.searchsorted(times, moments, side="right")
    for name, hours in WINDOWS.items():
        out[name] = upto - np.searchsorted(times, moments - np.timedelta64(hours, "h"), side="right")
    if len(times):
        last = np.where(upto > 0, times[np.maximum(upto - 1, 0)], np.datetime64("NaT"))
        out["hours_since"] = (moments - last) / np.timedelta64(1, "h")
    else:
        out["hours_since"] = np.full(len(moments), np.nan)
    return out


def main() -> None:
    object_of, _ = context.locations()
    pump_events = extract.extract_events(config.SENSOR_ALIASES["pump"])
    sources = {
        "pump": episodes_mod.build_episodes(pump_events),
        "fan": episodes_mod.build_episodes(extract.extract_events(config.SENSOR_ALIASES["fan"])),
        "phase": discovery.state_episodes(extract.extract_events(modules.PHASE_SENSOR), modules.PHASE_STATE),
        "flooded": discovery.state_episodes(pump_events, flood.FLOOD_STATE),
    }
    for frame in sources.values():
        frame["channel_id"] = frame["channel_id"].astype(str)
        frame["object"] = frame["channel_id"].map(object_of)
    streams = {name: frame.dropna(subset=["object"]).rename(columns={"episode_start": "start"}) for name, frame in sources.items()}
    everything = pd.concat([frame[["channel_id", "object", "episode_start"]] for frame in sources.values()]).dropna(subset=["object"])
    streams["station"] = clusters(sources["pump"].dropna(subset=["object"]), 2)
    streams["mass"] = clusters(everything, 5)
    pump_objects = sorted(streams["pump"]["object"].unique())
    log(f"pump objects {len(pump_objects)}, station outages {len(streams['station'])}, mass outages {len(streams['mass'])}")

    first, last = streams["pump"]["start"].min().ceil("D"), streams["pump"]["start"].max().floor("D")
    moments = pd.date_range(first + pd.Timedelta(days=30), last - HORIZON, freq=STEP)
    indexed = {name: times_by_object(frame, "start") for name, frame in streams.items()}
    empty = np.array([], dtype="datetime64[ns]")
    rows = []
    for key in pump_objects:
        stamp = moments.to_numpy(dtype="datetime64[ns]")
        part = {"object": key, "ts": moments}
        for name in streams:
            times = indexed[name].get(key, empty)
            for window, values in window_counts(times, stamp).items():
                part[f"{name}_{window}"] = values
        station = indexed["station"].get(key, empty)
        low = np.searchsorted(station, stamp, side="right")
        high = np.searchsorted(station, stamp + np.timedelta64(24, "h"), side="right")
        part["target"] = (high > low).astype(int)
        part["pumps"] = streams["pump"].loc[streams["pump"]["object"] == key, "channel_id"].nunique()
        part["phases"] = streams["phase"].loc[streams["phase"]["object"] == key, "channel_id"].nunique()
        rows.append(pd.DataFrame(part))
    data = pd.concat(rows, ignore_index=True)
    data["hour"] = data["ts"].dt.hour
    data["weekday"] = data["ts"].dt.weekday
    data["month"] = data["ts"].dt.month
    columns = [c for c in data.columns if c not in ("object", "ts", "target")]
    log(f"rows {len(data)}, base rate {data['target'].mean():.3f}")

    year = data["ts"].dt.year
    report = {"rows": int(len(data)), "objects": len(pump_objects), "base_rate": round(float(data["target"].mean()), 4)}
    periods = (("2025", 2025, (year == 2025).to_numpy()), ("2026H1", 2026, (year == 2026).to_numpy()))
    for period, before, test in periods:
        train = (data["ts"] < pd.Timestamp(f"{before}-01-01") - EMBARGO).to_numpy()
        y, ts = data.loc[test, "target"].to_numpy(), data.loc[test, "ts"].to_numpy()
        result = {"rule_station_7d": summary(y, data.loc[test, "station_7d"].to_numpy(), ts),
                  "rule_phase_1d": summary(y, data.loc[test, "phase_1d"].to_numpy(), ts)}
        for recipe in recipes.RECIPES:
            model = recipes.fit(recipe, data.loc[train, columns], data.loc[train, "target"])
            result[recipe] = summary(y, model.predict_proba(data.loc[test, columns]), ts)
            log(f"{period} {recipe}: {result[recipe]}")
        log(f"{period} rules: {result['rule_station_7d']} / {result['rule_phase_1d']}")
        report[period] = result
    best = max(recipes.RECIPES, key=lambda recipe: report["2025"][recipe]["avg_precision"])
    report["selected_on_2025"] = best
    report["selected_2026H1"] = report["2026H1"][best]
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(f"selected {best}: {report['selected_2026H1']}")


if __name__ == "__main__":
    main()
