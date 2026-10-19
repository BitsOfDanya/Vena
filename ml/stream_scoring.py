import json
import os
import re
import shutil
import time

import pandas as pd

import score_snapshot
from pipeline import config, extract
from pipeline.prospective import ProspectiveMonitor

EVENT_COLUMNS = ["channel_id", "ts", "alarm_flag", "raw_value"]
PROCESSED_RETENTION_DAYS = 7
CONTROL = "control.json"
ACK = "control.ack.json"
MARKER = ".replay_id"


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
        self.registry = None
        self.registry_day = None
        self.recent_states = {}

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

    def object_section(self, predictions):
        from pipeline import context, object_risk

        if not object_risk.available():
            return None, None
        day = pd.Timestamp(self.now).normalize()
        if self.registry_day != day:
            self.registry = object_risk.registry_from(self.events, context.locations()[0])
            since = day - pd.Timedelta(days=max(object_risk.STATE_WINDOWS) + 1)
            self.recent_states = {
                sensor: frame.loc[(frame["ts"] >= since) & frame["raw_value"].isin(states)]
                for sensor, states in object_risk.STATES.items()
                if (frame := self.events.get(sensor)) is not None
            }
            self.registry_day = day
        pumps = self.events.get(object_risk.SENSORS["flood"])
        recent_flood = None
        if pumps is not None:
            window = pumps.loc[pumps["ts"] >= self.now - pd.Timedelta(days=365), ["channel_id", "ts", "raw_value"]]
            recent_flood = object_risk.registry_from({object_risk.SENSORS["flood"]: window}, context.locations()[0])["flood"]
        return score_snapshot.object_section(self.now, predictions, self.recent_states, self.registry, recent_flood)

    def object_outcomes(self):
        from pipeline import context, object_risk

        if not object_risk.available():
            return {}
        since = self.monitor.start - pd.Timedelta(days=1)
        recent = {
            sensor: frame.loc[frame["ts"] >= since]
            for sensor, frame in self.events.items()
            if sensor in object_risk.SENSORS.values()
        }
        return self.monitor.evaluate_objects(object_risk.registry_from(recent, context.locations()[0]), self.now)

    def publish(self, output, carried, stream=None):
        predictions = list(self.predictions.values())
        objects, objects_meta = self.object_section(predictions)
        self.monitor.record_objects(objects, self.now)
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
            objects=objects,
            objects_meta=objects_meta,
        )
        os.replace(temporary, output)
        report = self.monitor.evaluate(self.events, self.now)
        report["objects"] = self.object_outcomes()
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


def read_json(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_json(path, payload):
    with open(f"{path}.tmp", "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
    os.replace(f"{path}.tmp", path)


def parse_control(control):
    if not isinstance(control, dict):
        return None
    replay_id = control.get("replay_id")
    if not isinstance(replay_id, str) or not replay_id:
        return None
    until = control.get("history_until")
    if until is None:
        return replay_id, None
    try:
        moment = pd.Timestamp(until)
    except (TypeError, ValueError):
        return None
    if pd.isna(moment):
        return None
    return replay_id, moment.tz_localize(None) if moment.tzinfo else moment


def control_reset(control, current):
    parsed = parse_control(control)
    if parsed is None or parsed[0] == current:
        return None
    return parsed


def archive_events(inbox, processed, label):
    target = os.path.join(processed, "archive-" + re.sub(r"[^A-Za-z0-9_.-]", "_", label))
    os.makedirs(target, exist_ok=True)
    for folder in (processed, inbox):
        for name in os.listdir(folder):
            if name.endswith(".jsonl"):
                os.replace(os.path.join(folder, name), os.path.join(target, name))
    expired = time.time() - PROCESSED_RETENTION_DAYS * 86400
    for name in os.listdir(processed):
        path = os.path.join(processed, name)
        if name.startswith("archive-") and path != target and os.path.getmtime(path) < expired:
            shutil.rmtree(path, ignore_errors=True)


def acknowledge(inbox, replay_id, history_end, error=None):
    payload = {
        "replay_id": replay_id,
        "history_end": pd.Timestamp(history_end).isoformat(),
        "ready_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    if error:
        payload["error"] = error
    write_json(os.path.join(inbox, ACK), payload)


def build_scorer(reference, history_until):
    try:
        return StreamScorer(reference, history_until), None
    except ValueError as error:
        log(f"history until {history_until} is empty, using the full journal: {error}")
        return StreamScorer(reference), str(error)


def run(output, inbox, poll_seconds=30, full_refresh_hours=24, history_until=None):
    os.makedirs(inbox, exist_ok=True)
    processed = os.path.join(inbox, "processed")
    os.makedirs(processed, exist_ok=True)
    heartbeat(os.path.join(os.path.dirname(output), "heartbeat"))
    reference = score_snapshot.channel_reference()
    control_path = os.path.join(inbox, CONTROL)
    marker = os.path.join(processed, MARKER)
    current = (read_json(marker) or {}).get("replay_id")
    control = parse_control(read_json(control_path))
    if control is not None:
        if control[0] != current:
            archive_events(inbox, processed, current or "live")
            write_json(marker, {"replay_id": control[0]})
        current, history_until = control
    scorer, error = build_scorer(reference, history_until)
    restored, _ = read_inbox(processed)
    if len(restored):
        scorer.ingest(restored)
    carried = full_sections(reference, scorer.history_end, output)
    scorer.refresh_history()
    scorer.score()
    scorer.publish(output, carried)
    if control is not None:
        acknowledge(inbox, current, scorer.history_end, error)
    log(f"initial snapshot: {len(scorer.predictions)} predictions, history until {scorer.history_end}")
    last_full = time.monotonic()
    while True:
        reset = control_reset(read_json(control_path), current)
        if reset is not None:
            archive_events(inbox, processed, current or "live")
            current, history_until = reset
            write_json(marker, {"replay_id": current})
            scorer, error = build_scorer(reference, history_until)
            carried = full_sections(reference, scorer.history_end, output)
            scorer.refresh_history()
            scorer.score()
            scorer.publish(output, carried)
            acknowledge(inbox, current, scorer.history_end, error)
            last_full = time.monotonic()
            log(f"history reset for {current}: {len(scorer.predictions)} predictions, history until {scorer.history_end}")
            continue
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
