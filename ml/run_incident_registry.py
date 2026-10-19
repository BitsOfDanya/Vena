import json
import os
import time

import pandas as pd

from pipeline import config, context, incidents

OUTPUT = os.path.join(config.ROOT, "results", "incident_registry.json")
RECENT_PER_KIND = 200


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(frame, rule):
    years = frame["t0"].dt.year.value_counts().sort_index()
    recent = frame.loc[frame["t0"] >= pd.Timestamp("2026-01-01")]
    out = {
        "label": rule["label"],
        "rule": rule["rule"],
        "total": int(len(frame)),
        "objects": int(frame["object"].nunique()),
        "per_year": {str(year): int(count) for year, count in years.items()},
        "recent_2026h1": int(len(recent)),
        "per_day_2026h1": round(len(recent) / 181, 2),
        "channels_median": float(frame["channels"].median()) if len(frame) else None,
        "top_objects": {str(k): int(v) for k, v in frame["object"].value_counts().head(10).items()},
    }
    if "temperature_confirmed" in frame:
        out["temperature_confirmed"] = int(frame["temperature_confirmed"].sum())
    if "max_minutes" in frame:
        out["long_over_30_minutes"] = int((frame["max_minutes"] >= 30).sum())
    return out


def records(kind, frame, limit=RECENT_PER_KIND):
    rows = []
    for row in frame.sort_values("t0", ascending=False).head(limit).itertuples(index=False):
        record = {"kind": kind, "object": str(row.object), "start": row.t0.isoformat(), "end": row.t1.isoformat(),
                  "channels": int(row.channels)}
        if hasattr(row, "temperature_confirmed"):
            record["temperature_confirmed"] = bool(row.temperature_confirmed)
        if hasattr(row, "max_minutes") and pd.notna(row.max_minutes):
            record["max_minutes"] = round(float(row.max_minutes), 1)
        rows.append(record)
    return rows


def main():
    rules = incidents.rules()
    object_of = context.locations()[0]
    report = {"journal_end": "2026-06-30", "incidents": {}, "recent": []}
    for kind, frame in incidents.registry(object_of).items():
        report["incidents"][kind] = summary(frame, rules[kind])
        report["recent"].extend(records(kind, frame))
        log(f"{kind}: {report['incidents'][kind]['total']} events on {report['incidents'][kind]['objects']} objects")
    report["recent"].sort(key=lambda row: row["start"], reverse=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
