import re

import numpy as np
import pandas as pd

from pipeline import states

ACCESS_SENSORS = ["КД Дверь", "КД Люк", "Стекло"]
GUARD_SENSOR = "Состояние охраны"
TRIGGER_STATES = {"Не замкнут"}
ARMED, DISARMED = "На охране", "Снято с охраны"
CHAIN_WINDOW = pd.Timedelta(minutes=10)
MIN_HISTORY = 50
WEIGHTS = {"rarity": 0.4, "breach_sensor": 0.25, "night": 0.2, "chain": 0.15}
ROUTE_GAP = pd.Timedelta(minutes=30)
PICKET_METERS = 10
PICKET = re.compile(r"ПК\s?(\d+)")


def object_of(tag):
    return str(tag).split("-", 1)[0] if isinstance(tag, str) and tag else None


def triggers(events, sensor_type, tag_by_channel):
    ev = events.sort_values(["channel_id", "ts"], kind="stable")
    triggered = ev["raw_value"].isin(TRIGGER_STATES)
    previous = triggered.groupby(ev["channel_id"], observed=True).shift(1, fill_value=False)
    onset = ev.loc[triggered & ~previous, ["channel_id", "ts"]].copy()
    onset["channel_id"] = onset["channel_id"].astype(str)
    onset["sensor_type"] = sensor_type
    onset["object"] = onset["channel_id"].map(tag_by_channel).map(object_of)
    return onset.dropna(subset=["object"])


def guard_states(events, tag_by_channel):
    events = events.assign(raw_value=states.normalize(events["raw_value"]).to_numpy())
    guard = events.loc[events["raw_value"].isin({ARMED, DISARMED, states.FAULT}), ["channel_id", "ts", "raw_value"]].copy()
    guard["object"] = guard["channel_id"].astype(str).map(tag_by_channel).map(object_of)
    guard = guard.dropna(subset=["object"]).rename(columns={"raw_value": "guard_state"})
    return guard[["object", "ts", "guard_state"]].sort_values("ts", kind="stable").reset_index(drop=True)


def _rarity(frame):
    bucket = frame["ts"].dt.dayofweek * 24 + frame["ts"].dt.hour
    prior_total = frame.groupby("channel_id", observed=True).cumcount()
    prior_bucket = frame.groupby([frame["channel_id"], bucket], observed=True).cumcount()
    expected = prior_total / 168.0
    rarity = np.clip(1.0 - prior_bucket / np.maximum(expected, 1e-9), 0.0, 1.0)
    return np.where(prior_total >= MIN_HISTORY, rarity, 0.5)


def assess(access_events, guard):
    frame = access_events.sort_values("ts", kind="stable").reset_index(drop=True)
    state = pd.merge_asof(frame, guard, on="ts", by="object", direction="backward")
    armed = state.loc[state["guard_state"] == ARMED].drop(columns="guard_state")

    armed = armed.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    armed["rarity"] = _rarity(armed)
    armed = armed.sort_values("ts", kind="stable").reset_index(drop=True)
    previous = armed.groupby("object", observed=True)["ts"].shift(1)
    previous_channel = armed.groupby("object", observed=True)["channel_id"].shift(1)
    armed["chain"] = ((armed["ts"] - previous) <= CHAIN_WINDOW) & (previous_channel != armed["channel_id"])
    armed["breach_sensor"] = armed["sensor_type"].isin({"КД Люк", "Стекло"})
    armed["night"] = (armed["ts"].dt.hour >= 22) | (armed["ts"].dt.hour < 6)
    armed["index"] = sum(weight * armed[name].astype(float) for name, weight in WEIGHTS.items())
    return armed


def picket(name):
    match = PICKET.search(name) if isinstance(name, str) else None
    return int(match.group(1)) if match else None


def routes(armed, name_by_channel):
    frame = armed.assign(name=armed["channel_id"].map(name_by_channel))
    frame = frame.assign(picket=frame["name"].map(picket)).dropna(subset=["picket", "object"]).sort_values("ts", kind="stable")
    gap = frame.groupby("object", observed=True)["ts"].diff()
    frame["route"] = (gap.isna() | (gap > ROUTE_GAP)).cumsum()
    result = []
    for _, steps in frame.groupby("route", sort=False):
        pickets = steps["picket"].astype(int).tolist()
        if len(set(pickets)) < 2:
            continue
        moves = np.sign(np.diff(pickets))
        moves = moves[moves != 0]
        direction = "increasing" if (moves > 0).all() else "decreasing" if (moves < 0).all() else "mixed"
        minutes = (steps["ts"].iloc[-1] - steps["ts"].iloc[0]).total_seconds() / 60
        distance = (max(pickets) - min(pickets)) * PICKET_METERS
        result.append({
            "object": steps["object"].iloc[0],
            "start": steps["ts"].iloc[0],
            "end": steps["ts"].iloc[-1],
            "direction": direction,
            "distance_m": distance,
            "speed_m_per_min": round(distance / minutes, 1) if minutes > 0 else None,
            "max_index": round(float(steps["index"].max()), 4),
            "night": bool(steps["night"].any()),
            "steps": [{"ts": row.ts, "channel_id": row.channel_id, "name": row.name, "picket": int(row.picket),
                       "sensor_type": row.sensor_type} for row in steps.itertuples()],
        })
    return result
