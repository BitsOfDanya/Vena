import numpy as np
import pandas as pd

from pipeline import config, episodes as episodes_mod, extract, features as features_mod
from pipeline import candidates as candidates_mod
from pipeline.targets import discovery

LOCKBOX_START = pd.Timestamp("2026-01-01")


def global_rates(events, target_state, train_end_year):
    train = events[events["ts"].dt.year <= train_end_year]
    if train.empty:
        return {"event": 0.0, "alarm": 0.0, "failure": 0.0}
    n_days = max((train["ts"].max() - train["ts"].min()).total_seconds() / 86400.0, 1.0)
    denom = n_days * max(train["channel_id"].nunique(), 1)
    return {"event": len(train) / denom, "alarm": float(train["alarm_flag"].sum()) / denom,
            "failure": float((train["raw_value"] == target_state).sum()) / denom}


def event_candidates(events, target_state, silence=True):
    parts = []
    for channel_id, g in events.groupby("channel_id", sort=False, observed=True):
        g = g.reset_index(drop=True)
        prev = g["raw_value"].shift(1)
        transition = (g["raw_value"] != prev) & prev.notna()
        burst = candidates_mod._burst_mask(g)
        alarm = g["alarm_flag"] == 1
        keep = (g["raw_value"] != target_state) & (transition | burst | alarm)
        cand = g.loc[keep, ["channel_id", "ts"]].copy()
        parts.append(cand)
        if silence:
            parts.append(candidates_mod._silence_checkpoints(g, channel_id)[["channel_id", "ts"]])
    non_empty = [p for p in parts if not p.empty]
    out = pd.concat(non_empty, ignore_index=True) if non_empty else pd.DataFrame(columns=["channel_id", "ts"])
    return out.drop_duplicates(subset=["channel_id", "ts"]).sort_values(["channel_id", "ts"]).reset_index(drop=True)


def build_frame(events, target_state, horizons=(6, 24, 72), silence=True, episodes=None):
    events = events.sort_values(["channel_id", "ts"]).reset_index(drop=True)
    if episodes is None:
        episodes = discovery.state_episodes(events, target_state)
    cand = event_candidates(events, target_state, silence=silence)
    rates = global_rates(events, target_state, config.TRAIN_YEARS[1])
    feat = features_mod.compute_features(cand, events, episodes, numeric_mode=False, duty_cycle_mode=False,
                                         global_rates=rates)
    for h in horizons:
        feat = episodes_mod.assign_targets(feat, episodes, h).rename(columns={"target": f"y{h}"})
    feat = feat.loc[feat["ts"] < LOCKBOX_START].reset_index(drop=True)
    return feat, episodes


def load_events(sensor_type):
    return extract.extract_events(sensor_type)
