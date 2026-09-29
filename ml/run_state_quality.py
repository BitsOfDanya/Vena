import json
import os
import time

import pandas as pd

from pipeline import config, extract, states
from pipeline.targets import access

OUTPUT = os.path.join(config.ROOT, "results", "state_quality.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def text_counts():
    con = extract._connect()
    extract._build_views(con)
    counts = con.execute("""
        SELECT c.тип_датчика AS sensor_type, e.значение_датчика AS value, e.тревожное AS alarm, count(*) AS n
        FROM events_all e JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
        WHERE TRY_CAST(replace(e.значение_датчика, ',', '.') AS DOUBLE) IS NULL
        GROUP BY 1, 2, 3""").df()
    gas = con.execute("""
        SELECT count(*) AS readings,
               sum(CASE WHEN v < 0 OR v > 100 THEN 1 ELSE 0 END) AS invalid,
               sum(CASE WHEN v >= 1 AND v <= 100 THEN 1 ELSE 0 END) AS above_alarm
        FROM (SELECT TRY_CAST(replace(e.значение_датчика, ',', '.') AS DOUBLE) AS v
              FROM events_all e JOIN channels c ON c.ид_канала_данных = e.ид_канала_данных
              WHERE c.тип_датчика = 'Газовый датчик') WHERE v IS NOT NULL""").df().iloc[0]
    con.close()
    return counts, gas


def door_flags_by_guard():
    reference = extract.channel_dictionary()
    tags = dict(zip(reference["ид_канала_данных"].astype(str), reference["тег_инженерной_системы"], strict=True))
    guard = access.guard_states(extract.extract_events(access.GUARD_SENSOR), tags)
    doors = extract.extract_events("КД Дверь")
    doors = doors.loc[doors["raw_value"] == "Не замкнут", ["channel_id", "ts", "alarm_flag"]].copy()
    doors["object"] = doors["channel_id"].astype(str).map(tags).map(access.object_of)
    doors = pd.merge_asof(doors.dropna(subset=["object"]).sort_values("ts"), guard, on="ts", by="object", direction="backward")
    grouped = doors.groupby(doors["guard_state"].fillna("нет данных"))["alarm_flag"].agg(["mean", "size"])
    return {state: {"alarm_share": round(float(row["mean"]), 4), "openings": int(row["size"])} for state, row in grouped.iterrows()}


def main() -> None:
    counts, gas = text_counts()
    report = states.summary(counts)
    report["gas"] = {
        "readings": int(gas["readings"]),
        "invalid_share": round(float(gas["invalid"] / max(gas["readings"], 1)), 6),
        "above_alarm_share": round(float(gas["above_alarm"] / max(gas["readings"], 1)), 6),
        "alarm_threshold_percent_methane": states.GAS_ALARM,
    }
    report["door_openings_by_guard_state"] = door_flags_by_guard()
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps({key: report[key] for key in ("known_state_share", "alarm_flag_agreement", "epoch_error_records", "gas")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
