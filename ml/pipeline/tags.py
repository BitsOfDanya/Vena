import re
import numpy as np
import pandas as pd

from pipeline import config


def parse_tag(tag):
    if tag is None or not isinstance(tag, str):
        return []
    cleaned = re.sub(r"\.$", "", tag)
    return cleaned.split(".")


def tag_group_key(tag, levels=config.TAG_GROUP_LEVELS):
    tokens = parse_tag(tag)
    if len(tokens) < levels:
        return None
    return ".".join(tokens[:levels])


def assign_groups(df):
    df = df.copy()
    df["tag_group"] = df["tag"].apply(tag_group_key)
    return df


def build_group_daily_features(df):
    d = df.copy()
    d["day"] = d["ts"].dt.floor("D")
    is_fail = (d["raw_value"] == config.FAULT_LITERAL).astype(int)
    is_alarm = d["alarm_flag"]
    agg = d.groupby(["tag_group", "day"]).agg(
        group_events=("channel_id", "count"),
        group_alarms=("alarm_flag", "sum"),
        group_failures=("raw_value", lambda s: (s == config.FAULT_LITERAL).sum()),
        group_channels_active=("channel_id", "nunique"),
    ).reset_index()
    fail_channels = d.assign(is_fail=is_fail).groupby(["tag_group", "day"])["is_fail"].apply(
        lambda s: (s > 0).sum() if len(s) else 0
    ).reset_index(name="group_channels_abnormal")
    agg = agg.merge(fail_channels, on=["tag_group", "day"], how="left")
    agg["fraction_channels_abnormal"] = agg["group_channels_abnormal"] / agg["group_channels_active"].replace(0, np.nan)
    agg = agg.sort_values(["tag_group", "day"]).reset_index(drop=True)

    def _shifted_roll(g):
        g = g.set_index("day")
        ev = g["group_events"].shift(1).fillna(0)
        al = g["group_alarms"].shift(1).fillna(0)
        fr = g["fraction_channels_abnormal"].shift(1).fillna(0)
        out = pd.DataFrame(index=g.index)
        out["neighbor_events_7d"] = ev.rolling(7, min_periods=1).sum()
        out["neighbor_alarms_7d"] = al.rolling(7, min_periods=1).sum()
        out["neighbor_fraction_abnormal_7d"] = fr.rolling(7, min_periods=1).mean()
        out["neighbor_event_rate_delta"] = ev.rolling(3, min_periods=1).mean() - ev.rolling(14, min_periods=1).mean()
        return out.reset_index()

    parts = []
    for tag_group_value, g in agg.groupby("tag_group", sort=False):
        rolled = _shifted_roll(g)
        rolled["tag_group"] = tag_group_value
        parts.append(rolled)
    result = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(
        columns=["day", "neighbor_events_7d", "neighbor_alarms_7d",
                 "neighbor_fraction_abnormal_7d", "neighbor_event_rate_delta", "tag_group"]
    )
    return result[["tag_group", "day", "neighbor_events_7d", "neighbor_alarms_7d",
                    "neighbor_fraction_abnormal_7d", "neighbor_event_rate_delta"]]


def attach_neighbor_features(candidates_df, group_daily):
    c = candidates_df.copy()
    c["day"] = c["ts"].dt.floor("D")
    merged = c.merge(group_daily, on=["tag_group", "day"], how="left")
    for col in ["neighbor_events_7d", "neighbor_alarms_7d", "neighbor_fraction_abnormal_7d", "neighbor_event_rate_delta"]:
        merged[col] = merged[col].fillna(0)
    return merged.drop(columns=["day"])
