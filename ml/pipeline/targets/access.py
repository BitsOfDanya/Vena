"""Unauthorized-access analytics for the security subsystem.

The journal has no intrusion labels, so this is a triage index for dispatcher
verification, not a probability. Entry-point triggers (a door or hatch opens, a
glass-break sensor fires) that happen while their object is armed are ranked by
how unusual the hour of the week is for the sensor, whether the entry point is a
hatch or a window, night time, and a chain of triggers across the object.

Disarming does not confirm an entry in this data: after an armed-time door
opening the object is disarmed within 15 minutes in only about 3% of cases, so
the index does not use it.
"""

import numpy as np
import pandas as pd

ACCESS_SENSORS = ["КД Дверь", "КД Люк", "Стекло"]
GUARD_SENSOR = "Состояние охраны"
TRIGGER_STATES = {"Не замкнут"}
ARMED, DISARMED = "На охране", "Снято с охраны"
CHAIN_WINDOW = pd.Timedelta(minutes=10)
MIN_HISTORY = 50
WEIGHTS = {"rarity": 0.4, "breach_sensor": 0.25, "night": 0.2, "chain": 0.15}


def object_of(tag):
    return str(tag).split("-", 1)[0] if isinstance(tag, str) and tag else None


def triggers(events, sensor_type, tag_by_channel):
    """Onsets of the triggered state: a door or hatch opens, a glass sensor fires."""
    ev = events.sort_values(["channel_id", "ts"], kind="stable")
    triggered = ev["raw_value"].isin(TRIGGER_STATES)
    previous = triggered.groupby(ev["channel_id"], observed=True).shift(1, fill_value=False)
    onset = ev.loc[triggered & ~previous, ["channel_id", "ts"]].copy()
    onset["channel_id"] = onset["channel_id"].astype(str)
    onset["sensor_type"] = sensor_type
    onset["object"] = onset["channel_id"].map(tag_by_channel).map(object_of)
    return onset.dropna(subset=["object"])


def guard_states(events, tag_by_channel):
    guard = events.loc[events["raw_value"].isin({ARMED, DISARMED}), ["channel_id", "ts", "raw_value"]].copy()
    guard["object"] = guard["channel_id"].astype(str).map(tag_by_channel).map(object_of)
    guard = guard.dropna(subset=["object"]).rename(columns={"raw_value": "guard_state"})
    return guard[["object", "ts", "guard_state"]].sort_values("ts", kind="stable").reset_index(drop=True)


def _rarity(frame):
    """How rare a trigger at this hour of the week is for the channel, from earlier triggers only."""
    bucket = frame["ts"].dt.dayofweek * 24 + frame["ts"].dt.hour
    prior_total = frame.groupby("channel_id", observed=True).cumcount()
    prior_bucket = frame.groupby([frame["channel_id"], bucket], observed=True).cumcount()
    expected = prior_total / 168.0
    rarity = np.clip(1.0 - prior_bucket / np.maximum(expected, 1e-9), 0.0, 1.0)
    return np.where(prior_total >= MIN_HISTORY, rarity, 0.5)


def assess(access_events, guard):
    """Score entry-point triggers that happen while their object is armed."""
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
