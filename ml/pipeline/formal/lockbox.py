from pathlib import Path

import pandas as pd

from pipeline import config, experiments
from pipeline.formal import data


class LockboxAlreadyOpened(RuntimeError):
    def __init__(self, marker):
        super().__init__(f"lockbox already opened: {marker}")
        self.marker = marker


def select_lockbox(frame, data_end, horizon_hours):
    cutoff = pd.Timestamp(data_end) - pd.Timedelta(hours=horizon_hours)
    keep = (frame["ts"] >= data.LOCKBOX_START) & (frame["ts"] <= cutoff)
    return frame.loc[keep].reset_index(drop=True)


def open_lockbox(device, horizon_hours, marker_path):
    marker = Path(marker_path)
    if marker.exists():
        raise LockboxAlreadyOpened(str(marker))
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
    frame = ctx.build(horizon_hours=horizon_hours)
    frame = select_lockbox(frame, ctx.events["ts"].max(), horizon_hours)
    frame["ttf_hours"] = data.time_to_next_failure_hours(frame, ctx.episodes)
    marker.write_text(f"{device} {horizon_hours} {len(frame)}\n")
    return ctx, frame
