import argparse
import json
import os
import time
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from pipeline import config, extract

SENSORS = [config.SENSOR_ALIASES[key] for key in ("pump", "fan", "smoke", "phase")]
OUTPUT = os.path.join(config.ROOT, "results", "stream_replay.json")


def load(start, end):
    con = extract._connect()
    extract._build_views(con)
    placeholders = ",".join("?" for _ in SENSORS)
    frame = con.execute(
        f"""
        SELECT e.ид_события AS event_id, e.ид_канала_данных AS channel_id,
               strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') AS ts,
               e.тревожное = 't' AS alarm, e.значение_датчика AS value
        FROM events_all e JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
        WHERE c.тип_датчика IN ({placeholders})
          AND strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') >= ?
          AND strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') < ?
        ORDER BY ts, e.ид_события
        """,
        [*SENSORS, start.to_pydatetime(), end.to_pydatetime()],
    ).df()
    return frame


def request(url, key, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://localhost:8100")
    parser.add_argument("--start", required=True, help="first replayed moment, e.g. 2026-06-01")
    parser.add_argument("--end", required=True, help="end of the replayed period")
    parser.add_argument("--speed", type=float, default=720.0, help="data seconds per real second")
    parser.add_argument("--tick", type=float, default=10.0, help="real seconds between batches")
    parser.add_argument("--timeout", type=float, default=300.0, help="latency budget in seconds")
    arguments = parser.parse_args()
    key = os.environ.get("VENA_TOKEN", "")
    base = arguments.url.rstrip("/")

    start, end = pd.Timestamp(arguments.start), pd.Timestamp(arguments.end)
    events = load(start, end)
    print(f"{len(events)} events from {start} to {end}", flush=True)
    step = pd.Timedelta(seconds=arguments.speed * arguments.tick)
    latencies, batches, clock = [], 0, start
    while clock < end:
        upper = min(clock + step, end)
        part = events.loc[(events["ts"] >= clock) & (events["ts"] < upper)]
        clock = upper
        if part.empty:
            continue
        before = request(f"{base}/api/v1/predictions/snapshot", key)
        body = {
            "batch_id": f"replay-{upper:%Y%m%d%H%M%S}",
            "event_count": int(len(part)),
            "last_event_at": part["ts"].max().isoformat(),
            "events": [
                {"event_id": str(row.event_id), "channel_id": str(row.channel_id), "ts": row.ts.isoformat(),
                 "value": str(row.value), "alarm": bool(row.alarm)}
                for row in part.itertuples()
            ],
        }
        sent = time.monotonic()
        request(f"{base}/api/v1/smvu/events", key, method="POST", body=body)
        while True:
            status = request(f"{base}/api/v1/predictions/snapshot", key)
            if status.get("snapshot_id") != before.get("snapshot_id") and status.get("prediction_time", "") >= part["ts"].max().isoformat()[:19]:
                latencies.append(time.monotonic() - sent)
                break
            if time.monotonic() - sent > arguments.timeout:
                latencies.append(float("inf"))
                break
            time.sleep(1.0)
        batches += 1
        print(f"batch {batches}: {len(part)} events up to {upper}, latency {latencies[-1]:.1f} s", flush=True)
        time.sleep(max(arguments.tick - (time.monotonic() - sent), 0))

    finite = [value for value in latencies if np.isfinite(value)]
    report = {
        "period": [start.isoformat(), end.isoformat()],
        "events": int(len(events)),
        "batches": batches,
        "speed": arguments.speed,
        "latency_seconds": {
            "median": round(float(np.median(finite)), 1) if finite else None,
            "p95": round(float(np.quantile(finite, 0.95)), 1) if finite else None,
            "max": round(float(max(finite)), 1) if finite else None,
        },
        "over_budget": int(sum(1 for value in latencies if value > arguments.timeout)),
        "budget_seconds": arguments.timeout,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
