import argparse
import json
import os
import time

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

import score_snapshot
from pipeline import artifacts, config, context, extract, incidents, object_risk

KINDS = {
    "fire": {"device": "smoke_alarm", "sensors": ("Датчик дыма", "Датчик температуры", "Состояние вентилятора", "Состояние фазы")},
    "flood": {"device": "flood", "sensors": ("Состояние насоса", "Состояние фазы")},
    "power": {"device": "phase", "sensors": ("Состояние фазы",)},
}
TEST_START = pd.Timestamp("2026-01-01")
LEAD = pd.Timedelta(hours=24)
TAIL = pd.Timedelta(hours=2)
CHECKPOINTS_HOURS = (24, 6, 1)
SWEEP_HOURS = 6
CATALOG_PER_KIND = 4
CATALOG_MAX_CHANNELS = 12
OUTPUT_DIR = os.path.join(config.ROOT, "results", "scenarios")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def pick(kind, registry, obj=None, date=None):
    frame = registry[kind]
    if obj:
        frame = frame.loc[frame["object"] == str(obj)]
    if date:
        frame = frame.loc[frame["t0"].dt.normalize() == pd.Timestamp(date)]
    if not obj and not date:
        frame = frame.loc[frame["t0"] >= TEST_START]
    if frame.empty:
        raise SystemExit("В реестре нет такого инцидента")
    return frame.sort_values("t0").iloc[-1]


def object_events(kind, obj, object_of, start, end):
    channels = sorted(ch for ch, o in object_of.items() if o == str(obj))
    frames = []
    for sensor in KINDS[kind]["sensors"]:
        table = ds.dataset(context._cache_path(sensor)).to_table(
            columns=["channel_id", "ts", "raw_value", "alarm_flag"],
            filter=ds.field("channel_id").isin(channels) & (ds.field("ts") >= start) & (ds.field("ts") <= end),
        )
        frames.append(table.to_pandas().assign(sensor=sensor))
    return pd.concat(frames, ignore_index=True).sort_values(["ts", "channel_id"], kind="stable").reset_index(drop=True)


def rule_check(kind, events, object_of):
    by_sensor = {sensor: part.drop(columns="sensor") for sensor, part in events.groupby("sensor")}
    empty = events.iloc[0:0].drop(columns="sensor")
    if kind == "fire":
        found = incidents.fire_incidents(object_of, by_sensor.get("Датчик дыма", empty), by_sensor.get("Датчик температуры", empty))
    elif kind == "flood":
        found = incidents.flood_incidents(object_of, by_sensor.get("Состояние насоса", empty))
    else:
        found = incidents.power_incidents(object_of, by_sensor.get("Состояние фазы", empty))
    return [{"object": row.object, "t0": row.t0.isoformat(), "channels": int(row.channels)} for row in found.itertuples()]


def object_ranking(rows, object_of):
    scores = {}
    for row in rows:
        obj = object_of.get(row["channel_id"])
        value = row.get("raw_score", row["score"])
        if obj is not None and value > scores.get(obj, (-1.0, None))[0]:
            scores[obj] = (value, row)
    return sorted(scores.items(), key=lambda item: item[1][0], reverse=True)


class Ranker:

    def __init__(self, kind):
        self.device, self.models, self.target = next(entry for entry in score_snapshot.DEVICES if entry[0] == KINDS[kind]["device"])
        events = extract.extract_events(score_snapshot.sensor_of(self.device))[["channel_id", "ts", "alarm_flag", "raw_value"]].copy()
        events["channel_id"] = events["channel_id"].astype(str)
        self.events = events
        self.reference = score_snapshot.channel_reference()

    def ranking(self, moment, object_of):
        recent = self.events.loc[(self.events["ts"] < moment) & (self.events["ts"] >= moment - pd.Timedelta(days=400))]
        active = set(recent.loc[recent["ts"] >= moment - pd.Timedelta(days=30), "channel_id"])
        rows = score_snapshot.score_rows(self.device, self.models, self.target, recent.loc[recent["channel_id"].isin(active)], self.reference)
        return object_ranking(rows, object_of)

    def place(self, obj, moment, object_of, ranking=None):
        ranking = self.ranking(moment, object_of) if ranking is None else ranking
        place = next((i + 1 for i, (key, _) in enumerate(ranking) if key == str(obj)), None)
        best = dict(ranking)[str(obj)][1] if place else None
        return {"moment": moment.isoformat(), "objects_ranked": len(ranking), "place": place,
                "score": best["score"] if best else None, "level": best["model_risk_level"] if best else None,
                "channel": best["channel_id"] if best else None, "model": self.models[0]}

    def lead(self, incident, object_of):
        out = []
        for hours in CHECKPOINTS_HOURS:
            result = self.place(incident["object"], incident["t0"] - pd.Timedelta(hours=hours), object_of)
            out.append({"hours_before": hours, **result})
        return out


class ObjectRanker:

    def __init__(self, kind, registry, object_of):
        self.kind, self.registry, self.object_of = kind, registry, object_of
        self.ready = kind in object_risk.available()
        self.nowcast = None
        if kind == "flood" and os.path.exists(os.path.join(artifacts.artifact_dir(object_risk.NOWCAST), "meta.json")):
            self.nowcast = artifacts.load_artifact(object_risk.NOWCAST)
            self.confirm = incidents.rules()["flood"]["window_minutes"]
        self.events = {}
        if self.ready:
            for sensor in object_risk.STATES:
                frame = object_risk.state_events(sensor).sort_values("ts", kind="stable").reset_index(drop=True)
                self.events[sensor] = (frame, frame["ts"].to_numpy())

    def recent(self, moment):
        day = pd.Timestamp(moment).normalize()
        lo, hi = (day - pd.Timedelta(days=max(object_risk.STATE_WINDOWS) + 1)).to_datetime64(), day.to_datetime64()
        return {sensor: frame.iloc[np.searchsorted(ts, lo):np.searchsorted(ts, hi)] for sensor, (frame, ts) in self.events.items()}

    def place(self, obj, moment, candidates):
        if not self.ready:
            return {}
        rows, _ = object_risk.score(self.registry, moment, self.object_of, events=self.recent(moment), kinds=[self.kind])
        rows = [row for row in rows if row["object_id"] in candidates]
        rows.sort(key=lambda row: row["rank"])
        place = next((i + 1 for i, row in enumerate(rows) if row["object_id"] == str(obj)), None)
        result = {"object_place": place, "object_probability": rows[place - 1]["probability"] if place else None,
                  "object_model": object_risk.KINDS[self.kind][1]}
        if self.nowcast is not None:
            model, meta = self.nowcast
            table = object_risk.nowcast_features(self.registry["flood"], sorted(candidates), moment, self.confirm)
            table["raw"] = model.predict_proba(table[meta["feature_columns"]])[:, 1]
            ranked = list(table.sort_values("raw", ascending=False, kind="stable")["object"])
            result["nowcast_place"] = ranked.index(str(obj)) + 1 if str(obj) in ranked else None
        return result


def evaluate(kind, incident, object_of):
    rule = incidents.rules()[kind]
    events = object_events(kind, incident["object"], object_of, incident["t0"] - LEAD, incident["t1"] + TAIL)
    report = {
        "kind": kind, "label": rule["label"], "rule": rule["rule"], "object": str(incident["object"]),
        "incident_start": incident["t0"].isoformat(), "incident_end": incident["t1"].isoformat(),
        "incident_channels": int(incident["channels"]), "events": int(len(events)),
        "events_by_sensor": {k: int(v) for k, v in events["sensor"].value_counts().items()},
        "rule_on_events": rule_check(kind, events, object_of),
        "lead": Ranker(kind).lead(incident, object_of),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if "temperature_confirmed" in incident:
        report["temperature_confirmed"] = bool(incident["temperature_confirmed"])
    for row in report["lead"]:
        log(f"за {row['hours_before']} ч: объект {report['object']} на {row['place']} месте из {row['objects_ranked']}, оценка {row['score']}")
    return report


def sweep(kind, registry, object_of, count):
    frame = registry[kind].loc[registry[kind]["t0"] >= TEST_START].sort_values("t0").reset_index(drop=True)
    if count < len(frame):
        frame = frame.iloc[np.unique(np.linspace(0, len(frame) - 1, count).round().astype(int))]
    ranker = Ranker(kind)
    objects = ObjectRanker(kind, registry, object_of)
    rows = []
    for item in frame.itertuples():
        moment = item.t0 - pd.Timedelta(hours=SWEEP_HOURS)
        ranking = ranker.ranking(moment, object_of)
        result = ranker.place(item.object, moment, object_of, ranking)
        result.update(objects.place(item.object, moment, {key for key, _ in ranking}))
        rows.append({"object": str(item.object), "incident_start": item.t0.isoformat(), "channels": int(item.channels), **result})
    places = pd.Series([row["place"] for row in rows], dtype="float")
    object_places = pd.Series([row.get("object_place") for row in rows], dtype="float")
    nowcast_places = pd.Series([row.get("nowcast_place") for row in rows], dtype="float")
    ranked = pd.Series([row["objects_ranked"] for row in rows], dtype="float")
    summary = {
        "kind": kind, "hours_before": SWEEP_HOURS, "incidents": len(rows),
        "period": f"{frame['t0'].min():%Y-%m-%d} — {frame['t0'].max():%Y-%m-%d}",
        "objects_ranked_median": float(ranked.median()) if len(ranked) else None,
        "share_top": {str(k): round(float((places <= k).mean()), 3) for k in (1, 3, 5)},
        "share_top_random": {str(k): round(float((k / ranked).clip(upper=1).mean()), 3) for k in (1, 3, 5)},
        "not_scored": int(places.isna().sum()),
        "incidents_detail": rows,
    }
    if objects.ready:
        summary["object_model"] = object_risk.KINDS[kind][1]
        summary["object_share_top"] = {str(k): round(float((object_places <= k).mean()), 3) for k in (1, 3, 5)}
    if objects.nowcast is not None:
        summary["nowcast_model"] = object_risk.NOWCAST
        summary["nowcast_share_top"] = {str(k): round(float((nowcast_places <= k).mean()), 3) for k in (1, 3, 5)}
    log(f"{kind}: {len(rows)} инцидентов, в топ-3 за {SWEEP_HOURS} ч {summary['share_top']['3']}, "
        f"по модели объекта {summary.get('object_share_top', {}).get('3')}, за 6 ч {summary.get('nowcast_share_top', {}).get('3')} "
        f"(случайно {summary['share_top_random']['3']})")
    return summary


def catalog(registry, object_of):
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {}, "items": [],
    }
    rules = incidents.rules()
    for kind in KINDS:
        path = os.path.join(OUTPUT_DIR, f"{kind}_sweep.json")
        if not os.path.exists(path):
            log(f"{kind}: нет {path}, сначала --sweep")
            continue
        with open(path, encoding="utf-8") as handle:
            result = json.load(handle)
        object_share = result.get("object_share_top", {}).get("3")
        nowcast_share = result.get("nowcast_share_top", {}).get("3")
        best = max(result["share_top"]["3"], object_share or 0.0, nowcast_share or 0.0)
        useful = best > result["share_top_random"]["3"]
        out["summary"][kind] = {"incidents": result["incidents"], "hours_before": result["hours_before"],
                                "share_top3": result["share_top"]["3"], "object_share_top3": object_share, "nowcast_share_top3": nowcast_share,
                                "share_top3_random": result["share_top_random"]["3"], "best_share_top3": best, "in_catalog": useful}
        if not useful:
            log(f"{kind}: за {result['hours_before']} ч объект в топ-3 не чаще случайного, в каталог не входит")
            continue
        def top(row):
            return min(row["place"] or 99, row.get("object_place") or 99, row.get("nowcast_place") or 99)

        hits = [row for row in result["incidents_detail"] if top(row) <= 3 and row["channels"] <= CATALOG_MAX_CHANNELS]
        chosen, objects = [], set()
        for row in sorted(hits, key=lambda r: (top(r), r["incident_start"]), reverse=False):
            if row["object"] not in objects:
                chosen.append(row)
                objects.add(row["object"])
            if len(chosen) == CATALOG_PER_KIND:
                break
        ranker = Ranker(kind)
        for row in chosen:
            frame = registry[kind]
            incident = frame.loc[(frame["object"] == row["object"]) & (frame["t0"] == pd.Timestamp(row["incident_start"]))].iloc[0]
            out["items"].append({
                "id": f"{kind}-{row['object']}-{incident['t0']:%Y%m%d%H%M}", "kind": kind, "label": rules[kind]["label"],
                "object": row["object"], "start": incident["t0"].isoformat(), "end": incident["t1"].isoformat(),
                "channels": int(incident["channels"]), "rule": rules[kind]["rule"],
                "before_hours": int(LEAD / pd.Timedelta(hours=1)), "after_hours": int(TAIL / pd.Timedelta(hours=1)),
                "lead": [{k: v for k, v in item.items() if k in ("hours_before", "place", "objects_ranked", "score", "level")}
                         for item in ranker.lead(incident, object_of) if item["place"] is not None],
                "object_place": row.get("object_place"),
                "object_probability": row.get("object_probability"),
                "nowcast_place": row.get("nowcast_place"),
            })
            log(f"каталог: {out['items'][-1]['id']}")
    shares = "; ".join(f"{rules[kind]['label'].lower()} — {item['best_share_top3']:.0%} против {item['share_top3_random']:.0%}"
                       for kind, item in out["summary"].items() if item["in_catalog"])
    out["note"] = ("Реальные инциденты января–июня 2026, которые модели не видели при обучении. В каталоге случаи, где объект "
                   f"стоял в топ-3 утреннего списка за {SWEEP_HOURS} ч до начала. По всем инцидентам полугодия так было: {shares} "
                   "при случайном порядке.")
    return out


def main():
    parser = argparse.ArgumentParser(description="Проверка модели на реальных инцидентах реестра")
    parser.add_argument("kind", nargs="?", choices=sorted(KINDS))
    parser.add_argument("--object", help="объект из реестра инцидентов")
    parser.add_argument("--date", help="дата инцидента, например 2026-04-10")
    parser.add_argument("--sweep", type=int, help="оценить N инцидентов тестового полугодия, равномерно по времени")
    parser.add_argument("--catalog", action="store_true", help="собрать каталог учебных сценариев по результатам --sweep")
    args = parser.parse_args()

    object_of = context.locations()[0]
    registry = incidents.registry(object_of)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if args.catalog:
        payload, name = catalog(registry, object_of), "catalog.json"
    elif not args.kind:
        raise SystemExit("Укажите тип инцидента: fire, flood или power")
    elif args.sweep:
        payload, name = sweep(args.kind, registry, object_of, args.sweep), f"{args.kind}_sweep.json"
    else:
        incident = pick(args.kind, registry, args.object, args.date)
        payload = evaluate(args.kind, incident, object_of)
        name = f"{args.kind}_{payload['object']}_{incident['t0']:%Y%m%d}.json"
    with open(os.path.join(OUTPUT_DIR, name), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=1)
    log(f"записано results/scenarios/{name}")


if __name__ == "__main__":
    main()
