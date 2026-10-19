import json
import os
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config, context, incidents, weather
from pipeline.formal import metrics as fm

OUTPUT = os.path.join(os.path.dirname(__file__), "flood_nowcast.json")
NAME = "object_flood_6h"
HORIZON = 6
STATES = ("Включен", "Выключен", "Работают все насосы в АНС", "Затоплен", "Неисправен", "Обесточен")
WINDOWS = (1, 3, 6, 24, 168)
START, END = pd.Timestamp("2019-02-01"), pd.Timestamp("2026-06-30 18:00")
EMBARGO = pd.Timedelta(days=7)
PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=31, min_child_samples=200, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7, n_jobs=4)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def counts_before(times, objects, index, hours):
    grid = np.zeros((len(objects), len(hours) + 1), dtype=np.float32)
    pos = np.searchsorted(hours.values, times.values.astype("datetime64[ns]"), side="right")
    np.add.at(grid, (index, pos), 1)
    return np.cumsum(grid, axis=1)[:, :-1]


def window(cum, w):
    shifted = np.concatenate([np.zeros((cum.shape[0], w), dtype=np.float32), cum[:, :-w]], axis=1)
    return cum - shifted


def build():
    object_of = context.locations()[0]
    events = incidents._events("Состояние насоса")
    events["object"] = events["channel_id"].map(object_of)
    events = events.dropna(subset=["object"])
    objects = sorted(events["object"].unique())
    obj_index = {o: i for i, o in enumerate(objects)}
    hours = pd.date_range(START, END, freq="h")
    features = {}
    for state in STATES:
        part = events.loc[events["raw_value"] == state]
        cum = counts_before(part["ts"], objects, part["object"].map(obj_index).to_numpy(), hours)
        for w in WINDOWS:
            features[f"{state}_{w}h"] = window(cum, w)
    flood = incidents.flood_incidents(object_of).query("object in @objects")
    known = flood["t0"] + pd.Timedelta(minutes=incidents.rules()["flood"]["window_minutes"])
    cum = counts_before(known, objects, flood["object"].map(obj_index).to_numpy(), hours)
    for w in (24, 168, 720):
        features[f"incidents_{w}h"] = window(cum, w)
    last = np.full((len(objects), len(hours)), np.nan, dtype=np.float64)
    for obj, group in flood.assign(known=known).groupby("object"):
        times = np.sort(group["known"].values.astype("datetime64[ns]"))
        pos = np.searchsorted(times, hours.values, side="left") - 1
        valid = pos >= 0
        hrs = np.full(len(hours), np.nan)
        hrs[valid] = (hours.values[valid] - times[pos[valid]]) / np.timedelta64(1, "h")
        last[obj_index[obj]] = hrs
    features["hours_since_incident"] = np.nan_to_num(last, nan=1e5).astype(np.float32)
    target = np.zeros((len(objects), len(hours)), dtype=np.int8)
    for obj, t0 in zip(flood["object"], flood["t0"], strict=True):
        lo = np.searchsorted(hours.values, (t0 - pd.Timedelta(hours=HORIZON)).to_datetime64(), side="left")
        hi = np.searchsorted(hours.values, t0.to_datetime64(), side="left")
        target[obj_index[obj], lo:hi] = 1
    days = weather.fetch_weather()[["day", "precipitation", "temp_mean"]].set_index("day")
    day_of = hours.normalize()
    prev = days.shift(1).reindex(day_of)
    prev3 = days["precipitation"].rolling(3).sum().shift(1).reindex(day_of)
    frame = pd.DataFrame({
        "object": np.repeat(objects, len(hours)),
        "ts": np.tile(hours.values, len(objects)),
        "target": target.ravel(),
        "hour": np.tile(hours.hour, len(objects)),
        "weekday": np.tile(hours.weekday, len(objects)),
        "month": np.tile(hours.month, len(objects)),
        "precip_prev_day": np.tile(prev["precipitation"].to_numpy(), len(objects)),
        "precip_prev_3d": np.tile(prev3.to_numpy(), len(objects)),
        "temp_prev_day": np.tile(prev["temp_mean"].to_numpy(), len(objects)),
    })
    for name, values in features.items():
        frame[name] = values.ravel()
    return frame, flood


def per_hour_topk(frame, score, k=3):
    ranked = frame.assign(score=score).sort_values(["ts", "score"], ascending=[True, False]).groupby("ts").head(k)
    return round(float(ranked["target"].mean()), 4)


def incident_share(frame, score, flood, start, end, k=3):
    data = frame.assign(score=score)
    data["place"] = data.groupby("ts")["score"].rank(ascending=False, method="first")
    lookup = data.set_index(["object", "ts"])["place"]
    rows = flood.loc[(flood["t0"] >= start) & (flood["t0"] < end)]
    places = []
    for obj, t0 in zip(rows["object"], rows["t0"], strict=True):
        moment = (t0 - pd.Timedelta(hours=HORIZON)).floor("h")
        if (obj, moment) in lookup.index:
            places.append(lookup.loc[(obj, moment)])
    places = np.array(places)
    return {"incidents": int(len(places)), "share_top3": round(float((places <= k).mean()), 3) if len(places) else None,
            "objects": int(frame["object"].nunique())}


def evaluate(frame, flood, test_mask, score, start, end):
    test = frame.loc[test_mask]
    frontier = fm.frontier_metrics(test["target"].to_numpy(), score)
    return {"base_rate": round(float(test["target"].mean()), 4), "avg_precision": round(float(frontier["pr_auc"]), 4),
            "roc_auc": round(float(frontier["roc_auc"]), 4), "precision_top3_per_hour": per_hour_topk(test, score),
            **incident_share(test, score, flood, start, end)}


def freeze(variant, columns, staging, final, frame, report):
    year = (frame["ts"] >= pd.Timestamp("2025-01-01")) & (frame["ts"] < pd.Timestamp("2026-01-01"))
    calibrator = calibration.fit_isotonic(staging.predict_proba(frame.loc[year, columns])[:, 1], frame.loc[year, "target"].to_numpy())
    test = (frame["ts"] >= pd.Timestamp("2026-01-01")) & (frame["ts"] < pd.Timestamp("2026-06-30 18:00"))
    probability = calibration.apply_isotonic(calibrator, final.predict_proba(frame.loc[test, columns])[:, 1])
    ece = calibration.expected_calibration_error(frame.loc[test, "target"].to_numpy(), probability)[0]
    result = report["periods"]["test_2026h1"][variant]
    metrics = {"selection_2025": report["periods"]["selection_2025"], "test_2026h1": {**result, "ece": round(float(ece), 4),
               "rule_avg_precision": report["periods"]["test_2026h1"]["rule"]["avg_precision"],
               "rule_share_top3": report["periods"]["test_2026h1"]["rule"]["share_top3"]}}
    model_config = {"label": "Подтопление станции за 6 ч", "kind": "flood", "scenario": "flooding", "recipe": "lightgbm",
                    "variant": variant, "horizon_hours": HORIZON, "calibrated": True, "target": report["target"],
                    "calibration": {"method": "isotonic", "fit_period": "2025"},
                    "features": "инциденты подтопления станции за 24, 168, 720 ч и часы с последнего (с момента подтверждения), час, день недели, месяц"}
    artifacts.save_artifact(NAME, final, columns, model_config, {"train_years": f"{config.TRAIN_YEARS[0]}-2025"}, metrics,
                            version=time.strftime("%Y-%m-%d"))
    joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(NAME), "calibrator.joblib"))
    log(f"{NAME} сохранена, ECE 2026H1 {ece:.4f}")


def main():
    frame, flood = build()
    log(f"panel {frame.shape}, positive share {frame['target'].mean():.4f}")
    history_cols = [c for c in frame.columns if c.startswith(("incidents_", "hours_since")) or c in ("hour", "weekday", "month")]
    all_cols = [c for c in frame.columns if c not in ("object", "ts", "target")]
    columns = {"history": history_cols, "nowcast": all_cols}
    report = {"horizon_hours": HORIZON, "target": "начало подтопления реестра на объекте в ближайшие 6 ч", "periods": {}}
    models = {}
    for period, train_end, test_start, test_end in (("selection_2025", "2025-01-01", "2025-01-01", "2026-01-01"),
                                                    ("test_2026h1", "2026-01-01", "2026-01-01", "2026-06-30 18:00")):
        train = frame["ts"] < pd.Timestamp(train_end) - EMBARGO
        test = (frame["ts"] >= pd.Timestamp(test_start)) & (frame["ts"] < pd.Timestamp(test_end))
        entry = {}
        for name, cols in columns.items():
            model = lgb.LGBMClassifier(**PARAMS).fit(frame.loc[train, cols], frame.loc[train, "target"])
            models[(period, name)] = model
            entry[name] = evaluate(frame, flood, test, model.predict_proba(frame.loc[test, cols])[:, 1],
                                   pd.Timestamp(test_start), pd.Timestamp(test_end))
            if name == "nowcast" and period == "test_2026h1":
                importance = pd.Series(model.feature_importances_, index=cols).sort_values(ascending=False)
                entry["top_features"] = importance.head(10).index.tolist()
        rule = frame.loc[test, "incidents_24h"] + frame.loc[test, "Затоплен_24h"] / 100.0
        entry["rule"] = evaluate(frame, flood, test, rule.to_numpy(), pd.Timestamp(test_start), pd.Timestamp(test_end))
        report["periods"][period] = entry
        log(f"{period}: " + ", ".join(f"{k} AP {v['avg_precision']} top3 {v['share_top3']}" for k, v in entry.items() if isinstance(v, dict)))
    sel = report["periods"]["selection_2025"]
    best = max(columns, key=lambda v: sel[v]["avg_precision"])
    report["selected"] = best
    report["decision"] = "в прод" if sel[best]["avg_precision"] > sel["rule"]["avg_precision"] else "в таблицу проверенных подходов"
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(f"{best}: {report['decision']}")
    if report["decision"] == "в прод":
        freeze(best, columns[best], models[("selection_2025", best)], models[("test_2026h1", best)], frame, report)


if __name__ == "__main__":
    main()
