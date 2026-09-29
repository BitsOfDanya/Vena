import json
import os
import time

import duckdb
import numpy as np
import pandas as pd

from pipeline import evaluate, recipes
from pipeline.formal import metrics as fm
from pipeline.targets import alarm, modules

SOURCE = "analysis/ml_ready/cache/events_Газовый_датчик.parquet"
HOURLY = "analysis/ml_ready/cache/gas_hourly.parquet"
OUTPUT = os.path.join(os.path.dirname(__file__), "gas_forecast.json")
HORIZON_HOURS = 24
EMBARGO = pd.Timedelta(hours=168)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def hourly():
    if not os.path.exists(HOURLY):
        con = duckdb.connect()
        con.execute(f"""
            COPY (
                SELECT channel_id, date_trunc('hour', ts) AS hour,
                       max(CASE WHEN v BETWEEN 0 AND 100 THEN v END) AS max_value,
                       avg(CASE WHEN v BETWEEN 0 AND 100 THEN v END) AS mean_value,
                       count(v) AS readings,
                       sum(CASE WHEN v < 0 OR v > 100 THEN 1 ELSE 0 END) AS invalid,
                       sum(CASE WHEN raw_value = 'Неисправен' THEN 1 ELSE 0 END) AS faults
                FROM (SELECT channel_id, ts, raw_value, TRY_CAST(replace(raw_value, ',', '.') AS DOUBLE) AS v FROM '{SOURCE}')
                GROUP BY 1, 2
            ) TO '{HOURLY}' (FORMAT parquet)""")
    frame = pd.read_parquet(HOURLY)
    frame["channel_id"] = frame["channel_id"].astype(str)
    return frame.sort_values(["channel_id", "hour"]).reset_index(drop=True)


def detections():
    con = duckdb.connect()
    events = con.execute(f"""
        SELECT channel_id, ts FROM '{SOURCE}' WHERE raw_value = 'Обнаружен газ' AND alarm_flag = 1 ORDER BY ts""").df()
    events["channel_id"] = events["channel_id"].astype(str)
    events["sensor_type"] = "Газовый датчик"
    events["maintenance"] = alarm.maintenance_series(events, modules.object_by_channel())
    return events


def rolling_features(frame):
    out = {}
    grouped = frame.groupby("channel_id", sort=False)
    for hours in (6, 24, 168):
        window = f"{hours}h"
        rolled = grouped.rolling(window, on="hour")
        out[f"max_{hours}h"] = rolled["max_value"].max().to_numpy()
        out[f"mean_{hours}h"] = rolled["mean_value"].mean().to_numpy()
        out[f"readings_{hours}h"] = rolled["readings"].sum().to_numpy()
        out[f"invalid_{hours}h"] = rolled["invalid"].sum().to_numpy()
        out[f"faults_{hours}h"] = rolled["faults"].sum().to_numpy()
        out[f"above_0_2_{hours}h"] = (frame["max_value"] >= 0.2).astype(float).groupby(frame["channel_id"]).transform(
            lambda s, h=hours: s.rolling(h, min_periods=1).sum()).to_numpy()
    features = pd.DataFrame(out, index=frame.index)
    features["max_1h"] = frame["max_value"].to_numpy()
    features["mean_1h"] = frame["mean_value"].to_numpy()
    features["trend_24h_vs_7d"] = features["mean_24h"] - features["mean_168h"]
    features["hour_of_day"] = frame["hour"].dt.hour
    features["weekday"] = frame["hour"].dt.weekday
    return features


def labels(frame, events):
    real = events.loc[~events["maintenance"]]
    starts = real.groupby("channel_id")["ts"].apply(lambda s: np.sort(s.to_numpy(dtype="datetime64[ns]"))).to_dict()
    past = events.groupby("channel_id")["ts"].apply(lambda s: np.sort(s.to_numpy(dtype="datetime64[ns]"))).to_dict()
    target = np.zeros(len(frame), dtype=int)
    detections_7d = np.zeros(len(frame))
    since = np.full(len(frame), np.nan)
    for channel, group in frame.groupby("channel_id", sort=False):
        rows = group.index.to_numpy()
        moment = (group["hour"] + pd.Timedelta(hours=1)).to_numpy(dtype="datetime64[ns]")
        times = starts.get(channel)
        if times is not None:
            first = np.searchsorted(times, moment, side="left")
            last = np.searchsorted(times, moment + np.timedelta64(HORIZON_HOURS, "h"), side="left")
            target[rows] = (last > first).astype(int)
        history = past.get(channel)
        if history is not None:
            upto = np.searchsorted(history, moment, side="left")
            detections_7d[rows] = upto - np.searchsorted(history, moment - np.timedelta64(168, "h"), side="left")
            last_seen = np.where(upto > 0, history[np.maximum(upto - 1, 0)], np.datetime64("NaT"))
            since[rows] = (moment - last_seen) / np.timedelta64(1, "h")
    return target, detections_7d, since


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5,))
    return {"avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "recall_at_precision_0.7": round(float(frontier["recall_at_precision_0.7"]), 4),
            "top5_per_day": top["precision_top5_per_day"]}


def main() -> None:
    frame = hourly()
    events = detections()
    log(f"hourly rows {len(frame)}, detections {len(events)}, planned maintenance share {events['maintenance'].mean():.3f}")
    features = rolling_features(frame)
    target, detections_7d, since = labels(frame, events)
    features["detections_7d"] = detections_7d
    features["hours_since_detection"] = since
    columns = list(features.columns)
    data = pd.concat([frame[["channel_id", "hour"]], features], axis=1).assign(target=target, ts=frame["hour"])
    year = data["ts"].dt.year
    report = {"rows": int(len(data)), "detections": int(len(events)),
              "maintenance_share": round(float(events["maintenance"].mean()), 4)}
    for period, before, test in (("2025", 2025, year == 2025),
                                 ("2026H1", 2026, (year == 2026) & (data["ts"] <= data["ts"].max() - pd.Timedelta(hours=HORIZON_HOURS)))):
        train = (data["ts"] < pd.Timestamp(f"{before}-01-01") - EMBARGO).to_numpy()
        test = test.to_numpy()
        y, ts = data.loc[test, "target"].to_numpy(), data.loc[test, "ts"].to_numpy()
        result = {"n": int(test.sum()), "base_rate": round(float(y.mean()), 5),
                  "rule_max_24h": summary(y, data.loc[test, "max_24h"].fillna(0).to_numpy(), ts),
                  "rule_detections_7d": summary(y, data.loc[test, "detections_7d"].to_numpy(), ts)}
        for recipe in ("lightgbm", "catboost"):
            model = recipes.fit(recipe, data.loc[train, columns], data.loc[train, "target"])
            result[recipe] = summary(y, model.predict_proba(data.loc[test, columns]), ts)
            log(f"{period} {recipe}: {result[recipe]}")
        report[period] = result
        log(f"{period}: {json.dumps({k: v for k, v in result.items() if k.startswith('rule')})}")
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
