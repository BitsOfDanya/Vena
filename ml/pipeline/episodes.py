import numpy as np
import pandas as pd

from pipeline import config


def build_episodes(df, gap_hours=config.EPISODE_GAP_HOURS):
    fail = df[df["raw_value"] == config.FAULT_LITERAL].sort_values(["channel_id", "ts"]).copy()
    if fail.empty:
        return pd.DataFrame(columns=["channel_id", "episode_start", "episode_end"])
    fail["gap_h"] = fail.groupby("channel_id", observed=True)["ts"].diff().dt.total_seconds() / 3600
    fail["new_episode"] = fail["gap_h"].isna() | (fail["gap_h"] > gap_hours)
    fail["episode_id"] = fail.groupby("channel_id", observed=True)["new_episode"].cumsum()
    grouped = fail.groupby(["channel_id", "episode_id"], observed=True)["ts"].agg(["min", "max"]).reset_index()
    grouped = grouped.rename(columns={"min": "episode_start", "max": "episode_end"})
    return grouped[["channel_id", "episode_start", "episode_end"]].sort_values(["channel_id", "episode_start"]).reset_index(drop=True)


def assign_targets(candidates, episodes, horizon_hours=config.DEFAULT_HORIZON_HOURS):
    horizon = pd.Timedelta(hours=horizon_hours)
    starts_by_channel = {
        cid: np.sort(g["episode_start"].values) for cid, g in episodes.groupby("channel_id", observed=True)
    } if len(episodes) else {}

    targets = np.zeros(len(candidates), dtype="int8")
    ts_values = candidates["ts"].values
    channel_values = candidates["channel_id"].values
    for cid, starts in starts_by_channel.items():
        mask = channel_values == cid
        if not mask.any():
            continue
        t = ts_values[mask]
        lo = np.searchsorted(starts, t, side="right")
        hi = np.searchsorted(starts, t + np.timedelta64(horizon), side="right")
        targets[mask] = (hi > lo).astype("int8")

    result = candidates.copy()
    result["target"] = targets
    return result
