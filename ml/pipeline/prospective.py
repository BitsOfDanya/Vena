import numpy as np
import pandas as pd

from pipeline import config, episodes as episodes_mod
from pipeline.targets import discovery

ALERT_LEVELS = {"critical", "high"}
COLUMNS = ["model_id", "channel_id", "scored_at", "horizon_hours", "probability", "level", "target_state", "sensor"]


def onsets(events, target_state):
    if events.empty:
        return pd.DataFrame(columns=["channel_id", "episode_start"])
    if target_state == config.FAULT_LITERAL:
        found = episodes_mod.build_episodes(events)
    else:
        found = discovery.state_episodes(events, target_state)
    return found[["channel_id", "episode_start"]].astype({"channel_id": str})


OBJECT_KINDS = {"object_power_24h": "power", "object_flood_24h": "flood", "object_fire_24h": "fire", "object_flood_6h": "flood"}
TOP = 3


def object_summary(frame, incidents, list_key, horizon):
    frame = frame.assign(outcome=frame["outcome"].astype(int))
    tops = frame.loc[frame["place"] <= TOP]
    lists = frame[list_key].nunique()
    covered = eligible = 0
    for row in incidents.itertuples():
        lead = frame.loc[(frame["object"] == row.object) & (frame["issued"] < row.t0) & (frame["issued"] >= row.t0 - horizon)]
        if len(lead):
            eligible += 1
            covered += int(lead.sort_values("issued").iloc[0]["place"] <= TOP)
    return {
        "lists": int(lists),
        "forecasts": int(len(frame)),
        "mean_probability": round(float(frame["probability"].mean()), 4),
        "event_rate": round(float(frame["outcome"].mean()), 4),
        "brier": round(float(np.mean((frame["probability"] - frame["outcome"]) ** 2)), 4),
        "top3_precision": round(float(tops["outcome"].mean()), 4) if len(tops) else None,
        "incidents": eligible,
        "incidents_total": int(len(incidents)),
        "incidents_top3": covered,
        "incident_recall_top3": round(covered / eligible, 4) if eligible else None,
    }


class ProspectiveMonitor:
    def __init__(self, start):
        self.start = pd.Timestamp(start)
        self.parts = []
        self.daily = {}
        self.hourly = {}

    def record_objects(self, rows, now):
        now = pd.Timestamp(now)
        hour = now.floor("h")
        for row in rows or []:
            day = pd.Timestamp(row["day"])
            if day >= self.start and (row["model_id"], day, row["object_id"]) not in self.daily:
                self.daily[(row["model_id"], day, row["object_id"])] = (float(row["probability"]), int(row["rank"]))
            if row.get("rank_6h") is not None and now >= self.start:
                self.hourly.setdefault((hour, row["object_id"]), (now, float(row["probability_6h"]), int(row["rank_6h"])))

    def evaluate_objects(self, registry, now):
        now = pd.Timestamp(now)
        report = {}
        daily = pd.DataFrame(
            [(model, day, obj, p, place) for (model, day, obj), (p, place) in self.daily.items()],
            columns=["model", "issued", "object", "probability", "place"],
        )
        for model, frame in daily.groupby("model"):
            kind = OBJECT_KINDS.get(model)
            events = registry.get(kind)
            frame = frame.assign(issued=pd.to_datetime(frame["issued"]))
            frame = frame.loc[frame["issued"] + pd.Timedelta(days=1) <= now]
            if events is None or frame.empty:
                continue
            days = set(zip(events["object"].astype(str), events["t0"].dt.normalize()))
            frame = frame.assign(outcome=[(obj, day) in days for obj, day in zip(frame["object"], frame["issued"])])
            span = events.loc[(events["t0"] >= frame["issued"].min()) & (events["t0"] < frame["issued"].max() + pd.Timedelta(days=1))]
            report[model] = object_summary(frame, span.assign(object=span["object"].astype(str)), "issued", pd.Timedelta(days=1))
        hourly = pd.DataFrame(
            [(issued, obj, p, place) for (_, obj), (issued, p, place) in self.hourly.items()],
            columns=["issued", "object", "probability", "place"],
        )
        if not hourly.empty:
            hourly = hourly.loc[pd.to_datetime(hourly["issued"]) + pd.Timedelta(hours=6) <= now]
        flood = registry.get("flood")
        if not hourly.empty and flood is not None:
            starts = {obj: np.sort(part["t0"].values) for obj, part in flood.assign(object=flood["object"].astype(str)).groupby("object")}

            def happened(row):
                times = starts.get(row.object)
                if times is None:
                    return False
                index = np.searchsorted(times, np.datetime64(row.issued), side="right")
                return bool(index < len(times) and times[index] <= np.datetime64(row.issued + pd.Timedelta(hours=6)))

            hourly = hourly.assign(outcome=[happened(row) for row in hourly.itertuples()])
            span = flood.loc[(flood["t0"] > hourly["issued"].min()) & (flood["t0"] <= hourly["issued"].max() + pd.Timedelta(hours=6))]
            report["object_flood_6h"] = object_summary(hourly, span.assign(object=span["object"].astype(str)), "issued", pd.Timedelta(hours=6))
        return report

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
