import json
import os
import time

import pandas as pd

from pipeline import config, extract
from pipeline.targets import alarm, modules

CACHE = os.path.join(config.ROOT, "analysis", "ml_ready", "cache", "alarm_events.parquet")
OUTPUT = os.path.join(config.ROOT, "results", "alarm_kpis.json")
SINCE = "2025-01-01"
MERGE = pd.Timedelta(minutes=10)
FLOOD_WINDOW = "10min"
FLOOD_ACTIVATIONS = 10
CHATTER_WINDOW = pd.Timedelta(seconds=60)
CHATTER_ACTIVATIONS = 3
ACCEPTABLE_PER_HOUR = 6
MANAGEABLE_PER_HOUR = 12
RECENT_DAYS = 30


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def alarm_events():
    if not os.path.exists(CACHE):
        con = extract._connect()
        extract._build_views(con)
        con.execute(f"""
            COPY (
                SELECT e.ид_канала_данных AS channel_id,
                       strptime(e.дата || ' ' || e.время, '%Y-%m-%d %H:%M:%S') AS ts,
                       e.значение_датчика AS raw_value,
                       c.тип_датчика AS sensor_type,
                       c.тип_инж_системы AS system_type
                FROM events_all e
                JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
                WHERE e.тревожное = 't' AND e.дата >= '{SINCE}'
            ) TO '{CACHE}' (FORMAT parquet)""")
        con.close()
    events = pd.read_parquet(CACHE)
    events["channel_id"] = events["channel_id"].astype(str)
    return events.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)


def activations(events):
    gap = events.groupby("channel_id")["ts"].diff()
    changed = events["raw_value"] != events.groupby("channel_id")["raw_value"].shift()
    start = gap.isna() | (gap > MERGE) | changed
    return events.loc[start].reset_index(drop=True)


def chattering(active):
    previous = active.groupby("channel_id")["ts"].shift(CHATTER_ACTIVATIONS - 1)
    burst = (active["ts"] - previous) <= CHATTER_WINDOW
    return set(active.loc[burst, "channel_id"])


def period_kpis(active, start, end, names=None):
    names = names or {}
    part = active.loc[(active["ts"] >= start) & (active["ts"] < end)]
    hours = pd.date_range(start, end, freq="h", inclusive="left")
    per_hour = part.set_index("ts").resample("h").size().reindex(hours, fill_value=0)
    per_window = part.set_index("ts").resample(FLOOD_WINDOW).size()
    floods = per_window[per_window > FLOOD_ACTIVATIONS]
    counts = part["channel_id"].value_counts()
    chatter = chattering(part)
    by_sensor = part["sensor_type"].value_counts().head(8)
    return {
        "start": str(start.date()),
        "end": str((end - pd.Timedelta(days=1)).date()),
        "activations": int(len(part)),
        "per_hour_mean": round(float(per_hour.mean()), 2),
        "per_hour_p95": round(float(per_hour.quantile(0.95)), 1),
        "per_hour_max": int(per_hour.max()) if len(per_hour) else 0,
        "hours_over_acceptable": round(float((per_hour > ACCEPTABLE_PER_HOUR).mean()), 4),
        "hours_over_manageable": round(float((per_hour > MANAGEABLE_PER_HOUR).mean()), 4),
        "flood_windows": int(len(floods)),
        "flood_share_of_time": round(len(floods) / max(len(per_window), 1), 4),
        "activations_in_floods": round(float(floods.sum() / max(len(part), 1)), 4),
        "top10_share": round(float(counts.head(10).sum() / max(len(part), 1)), 4),
        "top10_channels": [{"channel_id": key, "name": names.get(key), "activations": int(value)}
                           for key, value in counts.head(10).items()],
        "chattering_top": [{"channel_id": key, "name": names.get(key), "activations": int(counts[key])}
                           for key in sorted(chatter, key=lambda channel: -counts[channel])[:20]],
        "chattering_channels": len(chatter),
        "chattering_share": round(float(part["channel_id"].isin(chatter).mean()) if len(part) else 0.0, 4),
        "maintenance_share": round(float(part["maintenance"].mean()) if len(part) else 0.0, 4),
        "by_sensor_type": {key: int(value) for key, value in by_sensor.items()},
    }


def main() -> None:
    events = alarm_events()
    active = activations(events)
    active["maintenance"] = alarm.maintenance_series(active, modules.object_by_channel())
    log(f"alarm messages {len(events)}, activations {len(active)}")
    dictionary = extract.channel_dictionary()
    names = dict(zip(dictionary["ид_канала_данных"].astype(str), dictionary["название_датчика"], strict=True))
    end = active["ts"].max().normalize() + pd.Timedelta(days=1)
    months = pd.date_range(SINCE, end, freq="MS")
    report = {
        "definitions": {
            "activation": f"тревожное сообщение канала после паузы больше {int(MERGE.total_seconds() // 60)} мин или смены значения",
            "acceptable_per_hour": ACCEPTABLE_PER_HOUR,
            "manageable_per_hour": MANAGEABLE_PER_HOUR,
            "flood": f"больше {FLOOD_ACTIVATIONS} активаций за 10 мин",
            "chattering": f"{CHATTER_ACTIVATIONS} и более активаций канала за {int(CHATTER_WINDOW.total_seconds())} с",
            "scope": "вся диспетчерская, без разделения по пультам",
        },
        "recent": period_kpis(active, end - pd.Timedelta(days=RECENT_DAYS), end, names),
        "months": [period_kpis(active, start, min(start + pd.offsets.MonthBegin(1), end)) for start in months if start < end],
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    recent = report["recent"]
    log(f"last {RECENT_DAYS} days: {recent['per_hour_mean']} per hour, floods {recent['flood_share_of_time']}, "
        f"top10 {recent['top10_share']}, chattering {recent['chattering_channels']}")


if __name__ == "__main__":
    main()
