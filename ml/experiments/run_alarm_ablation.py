import json
import os
import time

import numpy as np
import pandas as pd

from pipeline.formal import metrics as fm
from pipeline.targets import modules
from pipeline.targets.model_zoo import LightGBMModel
from run_alarm_freeze import KEEP_CORROBORATED, TARGET, TEST_YEAR, TRAIN_END_YEAR, VALID_YEAR, WINDOW, operating, threshold_keeping

OUTPUT = os.path.join(os.path.dirname(__file__), "alarm_ablation.json")
SURGE = (pd.Timestamp("2021-04-01"), pd.Timestamp("2021-07-01"))
PRIORITY = ("Газовый датчик", "Датчик дыма", "Датчик температуры")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def quality(target, score, threshold):
    frontier = fm.frontier_metrics(target, score)
    return {"n": int(len(target)), "base_rate": round(float(target.mean()), 4),
            "avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            **operating(target, score, threshold)}


def main():
    frame = modules.build_alarm_frame(include_lockbox=True)
    columns = modules.alarm_feature_columns(frame)
    year = frame["ts"].dt.year
    complete = frame["ts"] <= frame["ts"].max() - np.timedelta64(WINDOW, "m")
    regular = ~frame["maintenance"].values
    surge = frame["ts"].between(*SURGE, inclusive="left").values
    train, valid, test = (year <= TRAIN_END_YEAR).values & regular, (year == VALID_YEAR).values & regular, ((year == TEST_YEAR) & complete).values & regular
    report = {"target": TARGET, "test": f"{TEST_YEAR}H1 без серий ППР", "surge": [SURGE[0].date().isoformat(), SURGE[1].date().isoformat()],
              "surge_alarms_in_train": int((train & surge).sum()), "train_alarms": int(train.sum()), "variants": {}}
    y_test = frame.loc[test, TARGET].values
    sensors = frame.loc[test, "sensor_type"].values
    for name, rows in {"все годы": train, "без апреля–июня 2021": train & ~surge}.items():
        model = LightGBMModel({"n_estimators": 300, "num_leaves": 63})
        model.fit(frame.loc[rows, columns], frame.loc[rows, TARGET].values)
        threshold = threshold_keeping(frame.loc[valid, TARGET].values, model.predict_proba(frame.loc[valid, columns]), KEEP_CORROBORATED)
        score = model.predict_proba(frame.loc[test, columns])
        entry = {"train_alarms": int(rows.sum()), "all": quality(y_test, score, threshold), "by_sensor": {}}
        for sensor in PRIORITY:
            mask = sensors == sensor
            if mask.any() and 0 < y_test[mask].sum() < mask.sum():
                entry["by_sensor"][sensor] = quality(y_test[mask], score[mask], threshold)
        report["variants"][name] = entry
        log(f"{name}: AP {entry['all']['avg_precision']}, " + ", ".join(f"{k}: {v['avg_precision']}" for k, v in entry["by_sensor"].items()))
    base, ablated = (report["variants"][k]["all"]["avg_precision"] for k in ("все годы", "без апреля–июня 2021"))
    report["decision"] = ("переобучить без всплеска 2021" if ablated - base > 0.005
                          else "оставить обучение на всех годах: всплеск 2021 не ухудшает модель")
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(report["decision"])


if __name__ == "__main__":
    main()
