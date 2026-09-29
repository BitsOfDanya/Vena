import json
import os
import time

import pandas as pd

import score_snapshot
from pipeline import config, extract
from pipeline.prospective import ProspectiveMonitor

EVENT_COLUMNS = ["channel_id", "ts", "alarm_flag", "raw_value"]
PROCESSED_RETENTION_DAYS = 7


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


class StreamScorer:
    def __init__(self, reference, history_until=None):
        self.reference = reference
        self.sensors = sorted({score_snapshot.sensor_of(device) for device, _, _ in score_snapshot.DEVICES})
        self.events = {}
        for sensor in self.sensors:
            frame = extract.extract_events(sensor)[EVENT_COLUMNS].copy()
            frame["channel_id"] = frame["channel_id"].astype(str)
            frame["raw_value"] = frame["raw_value"].astype(str)
            frame["alarm_flag"] = frame["alarm_flag"].astype("int8")
            if history_until is not None:
                frame = frame.loc[frame["ts"] < history_until]
            self.events[sensor] = frame.reset_index(drop=True)
        self.sensor_of_channel = {
            channel: info.get("sensor_type") for channel, info in reference.items() if info.get("sensor_type") in self.sensors
        }
        times = [frame["ts"].max() for frame in self.events.values() if len(frame)]
        if not times:
            raise ValueError("В журнале нет событий поддерживаемых моделей")
        self.history_end = max(times)
        self.now = self.history_end
        self.predictions = {}
        self.monitor = ProspectiveMonitor(self.history_end)
        self.history = None

    def refresh_history(self):
        self.history = score_snapshot.location_history(self.events, self.reference, self.now)

    def score(self, channels_by_sensor=None):
        rows = []
        for device, model_names, target_state in score_snapshot.DEVICES:
            sensor = score_snapshot.sensor_of(device)
            events = self.events[sensor]
            if channels_by_sensor is not None:
                channels = channels_by_sensor.get(sensor)
                if not channels:
                    continue
                events = events.loc[events["channel_id"].isin(channels)]
            scored = score_snapshot.score_rows(device, model_names, target_state, events, self.reference)
            for row in scored:
                row["target_state"] = target_state
                self.predictions[(row["model_id"], row["channel_id"])] = row
            rows.extend(scored)
        self.monitor.record(rows)
        return rows

    def ingest(self, batch):
        batch = batch.assign(sensor=batch["channel_id"].map(self.sensor_of_channel)).dropna(subset=["sensor"])
        affected = {}
        for sensor, part in batch.groupby("sensor"):
            part = part[EVENT_COLUMNS]
            merged = pd.concat([self.events[sensor], part], ignore_index=True)
            merged = merged.drop_duplicates(["channel_id", "ts", "raw_value", "alarm_flag"])
            self.events[sensor] = merged.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
            affected[sensor] = set(part["channel_id"])
        if len(batch):
            self.now = max(self.now, batch["ts"].max())
        return affected

    def publish(self, output, carried, stream=None):
        predictions = list(self.predictions.values())
        temporary = f"{output}.tmp"
        score_snapshot.write_snapshot(
            [{key: value for key, value in row.items() if key != "target_state"} for row in predictions],
            self.now,
            temporary,
            alarms=carried.get("alarms"),
            access_events=carried.get("access_events"),
            access_routes=carried.get("access_routes"),
            weather_forecast=carried.get("weather_forecast"),
            incidents=score_snapshot.incident_probabilities(predictions),
            stream=stream,
            history=self.history,
        )
        os.replace(temporary, output)
        report = self.monitor.evaluate(self.events, self.now)
        prospective = os.path.join(os.path.dirname(output), "prospective.json")
        with open(f"{prospective}.tmp", "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        os.replace(f"{prospective}.tmp", prospective)


def read_inbox(inbox):
    files = sorted(name for name in os.listdir(inbox) if name.endswith(".jsonl"))
    records = []
    for name in files:
        with open(os.path.join(inbox, name), encoding="utf-8") as handle:
            records.extend(json.loads(line) for line in handle if line.strip())
    if not records:
        return pd.DataFrame(columns=EVENT_COLUMNS), files
    frame = pd.DataFrame(records)
    batch = pd.DataFrame({
        "channel_id": frame["channel_id"].astype(str),
        "ts": pd.to_datetime(frame["ts"]),
        "alarm_flag": frame["alarm"].astype(bool).astype("int8"),
        "raw_value": frame["value"].astype(str),
    })
    return batch.sort_values("ts", kind="stable").reset_index(drop=True), files


def full_sections(reference, until, output):
    try:
        return {
            "alarms": score_snapshot.assess_alarms(reference, until),
            "access_events": score_snapshot.assess_access(reference, until),
            "access_routes": score_snapshot.assess_routes(reference, until),
            "weather_forecast": score_snapshot.forecast_weather(),
        }
    except Exception as error:  # noqa: BLE001
        log(f"alarm and access sections kept from the last snapshot: {error}")
        return carried_sections(output)


def heartbeat(path, interval=30):
    import threading

    def beat():
        while True:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
            time.sleep(interval)

    threading.Thread(target=beat, daemon=True).start()


def carried_sections(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    return {key: payload.get(key) for key in ("alarms", "access_events", "access_routes", "weather_forecast")}


def run(output, inbox, poll_seconds=30, full_refresh_hours=24, history_until=None):
    os.makedirs(inbox, exist_ok=True)
    processed = os.path.join(inbox, "processed")
    os.makedirs(processed, exist_ok=True)
    heartbeat(os.path.join(os.path.dirname(output), "heartbeat"))
    reference = score_snapshot.channel_reference()
    scorer = StreamScorer(reference, history_until)
    restored, _ = read_inbox(processed)
    if len(restored):
        scorer.ingest(restored)
    carried = full_sections(reference, scorer.history_end, output)
    scorer.refresh_history()
    scorer.score()
    scorer.publish(output, carried)
    log(f"initial snapshot: {len(scorer.predictions)} predictions, history until {scorer.history_end}")
    last_full = time.monotonic()
    while True:
        batch, files = read_inbox(inbox)
        if files:
            received = min(os.path.getmtime(os.path.join(inbox, name)) for name in files)
            affected = scorer.ingest(batch)
            rows = scorer.score(affected)
            scorer.publish(output, carried, stream={
                "events": int(len(batch)),
                "channels_rescored": len({row["channel_id"] for row in rows}),
                "received_at": pd.Timestamp(received, unit="s", tz="UTC").isoformat(),
                "published_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "latency_seconds": round(time.time() - received, 1),
            })
            for name in files:
                os.replace(os.path.join(inbox, name), os.path.join(processed, name))
            log(f"{len(batch)} events -> {len(rows)} forecasts rescored, data time {scorer.now}")
        if time.monotonic() - last_full >= full_refresh_hours * 3600:
            carried = full_sections(reference, scorer.now, output)
            scorer.refresh_history()
            scorer.score()
            scorer.publish(output, carried)
            last_full = time.monotonic()
        time.sleep(poll_seconds)


def main() -> None:
    output = os.environ.get("VENA_SNAPSHOT_PATH", os.path.join(config.ROOT, "results", "predictions", "snapshot.json"))
    inbox = os.environ.get("VENA_INBOX_DIR", os.path.join(config.ROOT, "inbox"))
    until = os.environ.get("VENA_STREAM_HISTORY_UNTIL")
    run(
        output,
        inbox,
        poll_seconds=float(os.environ.get("VENA_STREAM_POLL_SECONDS", "30")),
        full_refresh_hours=float(os.environ.get("VENA_STREAM_FULL_REFRESH_HOURS", "24")),
        history_until=pd.Timestamp(until) if until else None,
    )


if __name__ == "__main__":
    main()
