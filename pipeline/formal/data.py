import numpy as np
import pandas as pd

from pipeline import config, experiments

LOCKBOX_START = pd.Timestamp("2026-01-01")
PROTOCOL_TRAIN_END_YEAR = 2024
PROTOCOL_VALID_YEAR = 2025
HORIZONS = (6, 12, 24, 48, 72, 168)


def time_to_next_failure_hours(cand, episodes):
    ttf = np.full(len(cand), np.nan)
    ts = cand["ts"].values
    channels = cand["channel_id"].values
    for cid, g in episodes.groupby("channel_id", observed=True):
        mask = channels == cid
        if not mask.any():
            continue
        starts = np.sort(g["episode_start"].values)
        t = ts[mask]
        idx = np.searchsorted(starts, t, side="right")
        has = idx < len(starts)
        out = np.full(len(t), np.nan)
        out[has] = (starts[idx[has]] - t[has]) / np.timedelta64(1, "h")
        ttf[mask] = out
    return ttf


def drop_lockbox(frame):
    return frame.loc[frame["ts"] < LOCKBOX_START].reset_index(drop=True)


def load_research_frame(device, horizon_hours, with_neighbors=False):
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
    frame = ctx.build(horizon_hours=horizon_hours, with_neighbors=with_neighbors)
    frame = drop_lockbox(frame)
    frame["ttf_hours"] = time_to_next_failure_hours(frame, ctx.episodes)
    for h in HORIZONS:
        frame[f"y{h}"] = (frame["ttf_hours"] <= h).astype("int8")
    return ctx, frame


def protocol_masks(frame):
    year = frame["ts"].dt.year
    return (year <= PROTOCOL_TRAIN_END_YEAR).values, (year == PROTOCOL_VALID_YEAR).values


def fold_masks(frame, fold):
    year = frame["ts"].dt.year
    return (year <= fold["train_end"]).values, (year == fold["valid_year"]).values


def attach_extended_features(ctx, frame, lag_hours):
    from pipeline.formal import features_ext as fx

    parts = [
        fx.intensity_features(frame, ctx.events),
        fx.hourly_baseline_features(frame, ctx.events),
        fx.channel_history_rate(frame, frame["target"].values, lag_hours),
    ]
    ext = pd.concat(parts, axis=1).astype("float32")
    ext.index = frame.index
    return pd.concat([frame, ext], axis=1), list(ext.columns)


def markov_for_fold(ctx, frame, fold):
    from pipeline.formal import features_ext as fx

    train_end = pd.Timestamp(year=fold["train_end"], month=12, day=31, hour=23, minute=59, second=59)
    return fx.markov_features(frame, ctx.events, train_end).astype("float32")
