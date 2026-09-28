"""Prospective check of published forecasts against events that arrive later.

Every forecast issued after the history used for training is kept with its
channel, time, horizon, probability and level. Once the horizon has passed on
the incoming events, the forecast gets an outcome: did the target state start on
that channel within the horizon. On data after the training journal this is an
independent check that runs by itself as new events arrive.
"""

import numpy as np
import pandas as pd

from pipeline import config, episodes as episodes_mod
from pipeline.targets import discovery

ALERT_LEVELS = {"critical", "high"}
COLUMNS = ["model_id", "channel_id", "scored_at", "horizon_hours", "probability", "level", "target_state", "sensor"]


def onsets(events, target_state):
    """Starts of target-state episodes in an event frame."""
    if events.empty:
        return pd.DataFrame(columns=["channel_id", "episode_start"])
    if target_state == config.FAULT_LITERAL:
        found = episodes_mod.build_episodes(events)
    else:
        found = discovery.state_episodes(events, target_state)
    return found[["channel_id", "episode_start"]].astype({"channel_id": str})


class ProspectiveMonitor:
    def __init__(self, start):
        self.start = pd.Timestamp(start)
        self.parts = []

    def record(self, rows):
        fresh = [
            {
                "model_id": row["model_id"],
                "channel_id": str(row["channel_id"]),
                "scored_at": pd.Timestamp(row["scored_at"]),
                "horizon_hours": int(row["horizon_hours"]),
                "probability": float(row["score"]),
                "level": row["model_risk_level"],
                "target_state": row.get("target_state"),
                "sensor": row.get("sensor_type"),
            }
            for row in rows
            if pd.Timestamp(row["scored_at"]) > self.start and row.get("horizon_hours")
        ]
        if fresh:
            self.parts.append(pd.DataFrame(fresh, columns=COLUMNS))

    def evaluate(self, events_by_sensor, now):
        """Metrics of every model whose forecasts have a complete horizon by `now`."""
        if not self.parts:
            return {"start": self.start.isoformat(), "now": pd.Timestamp(now).isoformat(), "models": {}}
        issued = pd.concat(self.parts, ignore_index=True)
        now = pd.Timestamp(now)
        report = {}
        for (model_id, target_state, sensor, horizon), group in issued.groupby(
            ["model_id", "target_state", "sensor", "horizon_hours"], dropna=False
        ):
            window = pd.Timedelta(hours=int(horizon))
            events = events_by_sensor.get(sensor)
            if events is None:
                continue
            recent = events.loc[(events["ts"] > self.start) & events["channel_id"].isin(set(group["channel_id"]))]
            starts = onsets(recent, target_state)
            starts = starts.loc[starts["episode_start"] > self.start]
            matured = group.loc[group["scored_at"] + window <= now].copy()
            if matured.empty:
                continue
            by_channel = {key: np.sort(part["episode_start"].values) for key, part in starts.groupby("channel_id")}

            def happened(row):
                times = by_channel.get(row.channel_id)
                if times is None:
                    return 0
                begin, end = np.datetime64(row.scored_at), np.datetime64(row.scored_at + window)
                index = np.searchsorted(times, begin, side="right")
                return int(index < len(times) and times[index] <= end)

            matured["outcome"] = [happened(row) for row in matured.itertuples()]
            alerts = matured.loc[matured["level"].isin(ALERT_LEVELS)]
            # Recall counts episodes whose full look-back window lies after the start.
            eligible = starts.loc[starts["episode_start"] - window >= self.start]
            alert_times = {key: np.sort(part["scored_at"].values) for key, part in alerts.groupby("channel_id")}
            warned = 0
            for start in eligible.itertuples():
                times = alert_times.get(start.channel_id)
                if times is None:
                    continue
                begin, end = np.datetime64(start.episode_start - window), np.datetime64(start.episode_start)
                index = np.searchsorted(times, begin, side="left")
                warned += int(index < len(times) and times[index] < end)
            report[model_id] = {
                "forecasts": int(len(matured)),
                "event_rate": round(float(matured["outcome"].mean()), 4),
                "mean_probability": round(float(matured["probability"].mean()), 4),
                "brier": round(float(np.mean((matured["probability"] - matured["outcome"]) ** 2)), 4),
                "alerts": int(len(alerts)),
                "alert_precision": round(float(alerts["outcome"].mean()), 4) if len(alerts) else None,
                "episodes": int(len(eligible)),
                "episodes_warned": warned,
                "episode_recall": round(warned / len(eligible), 4) if len(eligible) else None,
            }
        return {"start": self.start.isoformat(), "now": now.isoformat(), "models": report}
