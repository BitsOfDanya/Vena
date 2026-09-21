import numpy as np
import pandas as pd

from pipeline import config


def _is_numeric_dominant(sensor_type):
    return sensor_type in config.NUMERIC_DOMINANT_SENSOR_TYPES


def _state_transition_mask(g, numeric_mode):
    if numeric_mode:
        numeric = pd.to_numeric(g["raw_value"], errors="coerce")
        std = numeric.rolling(20, min_periods=5).std().shift(1)
        prev = numeric.shift(1)
        z = (numeric - prev).abs() / std.replace(0, np.nan)
        return (z > 3).fillna(False)
    prev = g["raw_value"].shift(1)
    return (g["raw_value"] != prev) & prev.notna()


def _burst_mask(g):
    gap = g["ts"].diff().dt.total_seconds()
    threshold = gap.expanding(min_periods=config.BURST_MIN_HISTORY_EVENTS).quantile(
        config.BURST_INTERARRIVAL_PERCENTILE / 100
    ).shift(1)
    return (gap < threshold).fillna(False)


def _recovery_mask(g):
    prev = g["raw_value"].shift(1)
    return (prev == config.FAULT_LITERAL) & (g["raw_value"] != config.FAULT_LITERAL)


def _silence_checkpoints(g, channel_id):
    gaps = g["ts"].diff().dt.total_seconds() / 3600
    rows = []
    threshold = config.SILENCE_CHECKPOINT_HOURS
    for idx in np.where(gaps > threshold)[0]:
        start = g["ts"].iloc[idx - 1]
        end = g["ts"].iloc[idx]
        n_checkpoints = min(int((end - start).total_seconds() // 3600 // threshold), config.SILENCE_MAX_CHECKPOINTS)
        for k in range(1, n_checkpoints + 1):
            rows.append(start + pd.Timedelta(hours=threshold * k))
    if not rows:
        return pd.DataFrame(columns=["channel_id", "ts", "trigger"])
    return pd.DataFrame({"channel_id": channel_id, "ts": rows, "trigger": "silence"})


TRIGGER_TYPES = ["alarm", "fault_adjacent", "recovery", "burst", "transition", "silence"]


def generate_candidates(df, sensor_type, exclude_triggers=None):
    exclude_triggers = set(exclude_triggers or [])
    numeric_mode = _is_numeric_dominant(sensor_type)
    parts = []
    silence_parts = []
    for channel_id, g in df.groupby("channel_id", sort=False, observed=True):
        g = g.reset_index(drop=True)
        false_series = pd.Series(False, index=g.index)
        transition = _state_transition_mask(g, numeric_mode) if "transition" not in exclude_triggers else false_series
        burst = _burst_mask(g) if "burst" not in exclude_triggers else false_series
        recovery = _recovery_mask(g) if "recovery" not in exclude_triggers else false_series
        alarm = (g["alarm_flag"] == 1) if "alarm" not in exclude_triggers else false_series
        fault_adjacent = g["raw_value"].isin(config.FAULT_ADJACENT_LITERALS) if "fault_adjacent" not in exclude_triggers else false_series
        not_fault = g["raw_value"] != config.FAULT_LITERAL

        trigger_mask = not_fault & (transition | burst | recovery | alarm | fault_adjacent)
        cand = g.loc[trigger_mask, ["channel_id", "ts"]].copy()
        trigger_label = np.select(
            [alarm[trigger_mask], fault_adjacent[trigger_mask], recovery[trigger_mask],
             burst[trigger_mask], transition[trigger_mask]],
            ["alarm", "fault_adjacent", "recovery", "burst", "transition"],
            default="other",
        )
        cand["trigger"] = trigger_label
        parts.append(cand)
        if "silence" not in exclude_triggers:
            silence_parts.append(_silence_checkpoints(g, channel_id))

    non_empty = [p for p in parts + silence_parts if not p.empty]
    candidates = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame(columns=["channel_id", "ts", "trigger"])
    candidates = candidates.drop_duplicates(subset=["channel_id", "ts"]).sort_values(["channel_id", "ts"]).reset_index(drop=True)
    return candidates
