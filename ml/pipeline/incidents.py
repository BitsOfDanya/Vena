import json
import os

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from pipeline import config, context
from pipeline.targets import alarm

CONFIG = os.path.join(config.ROOT, "configs", "incidents.json")


def rules():
    with open(CONFIG, encoding="utf-8") as handle:
        return json.load(handle)


def _events(sensor_type, states=None):
    columns = ["channel_id", "ts", "raw_value"]
    dataset = ds.dataset(context._cache_path(sensor_type))
    flt = ds.field("raw_value").isin(states) if states else None
    frame = dataset.to_table(columns=columns, filter=flt).to_pandas()
    frame["channel_id"] = frame["channel_id"].astype(str)
    return frame.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)


def onsets(events, state, gap_minutes):
    hits = events.loc[events["raw_value"] == state, ["channel_id", "ts"]]
    previous = hits.groupby("channel_id")["ts"].shift(1)
    fresh = previous.isna() | (hits["ts"] - previous > pd.Timedelta(minutes=gap_minutes))
    return hits.loc[fresh].reset_index(drop=True)


def bursts(onset, object_of, window_minutes, longest=None):
    frame = onset.assign(object=onset["channel_id"].map(object_of)).dropna(subset=["object"])
    frame = frame.sort_values(["object", "ts"], kind="stable")
    gap = frame.groupby("object")["ts"].diff() > pd.Timedelta(minutes=window_minutes)
    frame["burst"] = (gap | frame["object"].ne(frame["object"].shift())).cumsum()
    grouped = frame.groupby("burst")
    out = pd.DataFrame({
        "object": grouped["object"].first(),
        "t0": grouped["ts"].min(),
        "t1": grouped["ts"].max(),
        "channels": grouped["channel_id"].nunique(),
    })
    if longest:
        out[f"max_{longest}"] = grouped[longest].max()
    return out.reset_index(drop=True)


def _maintenance(frame):
    count, _ = alarm.MAINTENANCE_SERIES["Датчик дыма"]
    work = (frame["t0"].dt.weekday < 5) & frame["t0"].dt.hour.between(alarm.WORK_HOURS[0], alarm.WORK_HOURS[1] - 1)
    return work & (frame["channels"] >= count)


def _temperature_confirmed(fire, rule, object_of, events=None):
    events = _events("Датчик температуры") if events is None else events
    value = pd.to_numeric(events["raw_value"].str.replace(",", ".", regex=False), errors="coerce")
    hot = events["raw_value"].isin(rule["temperature_states"]) | value.between(rule["temperature_min"], rule["temperature_max"])
    hot = events.loc[hot, ["channel_id", "ts"]].assign(object=lambda f: f["channel_id"].map(object_of)).dropna(subset=["object"])
    times = {key: group["ts"].to_numpy(dtype="datetime64[ns]") for key, group in hot.sort_values("ts").groupby("object")}
    before = np.timedelta64(rule["temperature_before_minutes"], "m")
    after = np.timedelta64(rule["temperature_after_minutes"], "m")
    out = np.zeros(len(fire), dtype=bool)
    for i, (obj, t0, t1) in enumerate(zip(fire["object"], fire["t0"].to_numpy(), fire["t1"].to_numpy(), strict=True)):
        series = times.get(obj)
        if series is not None:
            lo, hi = np.searchsorted(series, t0 - before), np.searchsorted(series, t1 + after, side="right")
            out[i] = hi > lo
    return out


def fire_incidents(object_of=None, smoke=None, temperature=None):
    rule = rules()["fire"]
    object_of = object_of or context.locations()[0]
    smoke = _events(rule["sensor"], [rule["state"]]) if smoke is None else smoke
    onset = onsets(smoke, rule["state"], rule["onset_gap_minutes"])
    frame = bursts(onset, object_of, rule["window_minutes"])
    if rule["exclude_maintenance"]:
        frame = frame.loc[~_maintenance(frame)]
    frame = frame.loc[frame["channels"] >= rule["min_channels"]].reset_index(drop=True)
    frame["temperature_confirmed"] = _temperature_confirmed(frame, rule, object_of, temperature)
    return frame.assign(kind="fire")


def flood_incidents(object_of=None, events=None):
    rule = rules()["flood"]
    object_of = object_of or context.locations()[0]
    events = _events(rule["sensor"]) if events is None else events
    flooded = events["raw_value"].eq(rule["state"])
    channel = events["channel_id"]
    start = flooded & ~(flooded.shift(fill_value=False) & channel.eq(channel.shift()))
    run = start.cumsum().where(flooded)
    following = events["ts"].shift(-1).where(channel.eq(channel.shift(-1)))
    episodes = pd.DataFrame({"channel_id": channel, "ts": events["ts"], "end": following, "run": run}).dropna(subset=["run"])
    episodes = episodes.groupby("run").agg(channel_id=("channel_id", "first"), ts=("ts", "first"), end=("end", "last"))
    episodes["minutes"] = (episodes["end"] - episodes["ts"]).dt.total_seconds() / 60.0
    frame = bursts(episodes[["channel_id", "ts", "minutes"]], object_of, rule["window_minutes"], longest="minutes")
    keep = (frame["channels"] >= rule["min_channels"]) | (frame["max_minutes"] >= rule["min_duration_minutes"])
    return frame.loc[keep].reset_index(drop=True).assign(kind="flood")


def power_incidents(object_of=None, events=None):
    rule = rules()["power"]
    object_of = object_of or context.locations()[0]
    events = _events(rule["sensor"], [rule["state"]]) if events is None else events
    onset = onsets(events, rule["state"], rule["onset_gap_minutes"])
    frame = bursts(onset, object_of, rule["window_minutes"])
    return frame.loc[frame["channels"] >= rule["min_channels"]].reset_index(drop=True).assign(kind="power")


def registry(object_of=None):
    object_of = object_of or context.locations()[0]
    return {
        "fire": fire_incidents(object_of),
        "flood": flood_incidents(object_of),
        "power": power_incidents(object_of),
    }
