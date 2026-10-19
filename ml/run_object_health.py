import json
import os
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments.run_object_selection import PARAMS
from pipeline import artifacts, calibration, config, context, incidents, object_risk
from pipeline.formal import metrics as fm
from run_object_level import state_table

SELECTION = os.path.join(config.ROOT, "experiments", "object_selection.json")
HISTORY = os.path.join(config.ROOT, "results", "health_history.json")
REPORT = os.path.join(config.ROOT, "results", "object_health.json")
NAME = "object_health"
TEST_START, TEST_END = pd.Timestamp("2026-01-02"), pd.Timestamp("2026-06-29")
HISTORY_START, HISTORY_END = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-06-30")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def ties(frame, column):
    per_day = frame.groupby("day")[column]
    modal = per_day.agg(lambda values: values.value_counts().iloc[0] / len(values))
    distinct = per_day.nunique()
    overall = frame[column].value_counts(normalize=True)
    return {"modal_share_per_day": round(float(modal.mean()), 3), "distinct_per_day": float(distinct.median()),
            "top_value": int(overall.index[0]), "top_value_share": round(float(overall.iloc[0]), 3)}


def quality(target, probability):
    frontier = fm.frontier_metrics(target, probability)
    return {"base_rate": round(float(np.mean(target)), 4), "mean_probability": round(float(np.mean(probability)), 4),
            "avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "brier": round(float(np.mean((probability - target) ** 2)), 4),
            "ece": round(float(calibration.expected_calibration_error(target, probability)[0]), 4)}


def kind_probabilities(table, selection):
    staging_rows = table["day"] < pd.Timestamp("2024-12-31")
    out_2025, out_test = {}, {}
    year = table["day"].dt.year == 2025
    test = (table["day"] >= HISTORY_START) & (table["day"] <= HISTORY_END)
    for kind, (_, name, _) in object_risk.KINDS.items():
        model, meta = artifacts.load_artifact(name)
        columns = meta["feature_columns"]
        params = selection[kind].get("params", {}).get(meta["model_config"]["variant"], PARAMS)
        staging = lgb.LGBMClassifier(**params).fit(table.loc[staging_rows, columns], table.loc[staging_rows, f"y_{kind}"].astype(int))
        calibrator = artifacts.load_calibrator(name)
        out_2025[kind] = np.clip(calibration.apply_isotonic(calibrator, staging.predict_proba(table.loc[year, columns])[:, 1]), 0, 1)
        out_test[kind] = np.clip(calibration.apply_isotonic(calibrator, model.predict_proba(table.loc[test, columns])[:, 1]), 0, 1)
        log(f"{kind}: вероятности 2025 и 2026H1")
    return year, test, out_2025, out_test


def combine(parts):
    survive = np.ones_like(next(iter(parts.values())))
    for value in parts.values():
        survive = survive * (1 - value)
    return 1 - survive


def main():
    object_of = context.locations()[0]
    registry = incidents.registry(object_of)
    table = state_table(registry, object_of)
    table["y_any"] = table[[f"y_{kind}" for kind in object_risk.KINDS]].any(axis=1).astype(int)
    selection = json.load(open(SELECTION, encoding="utf-8"))["variants"]
    year, test, p2025, ptest = kind_probabilities(table, selection)
    raw_2025 = combine(p2025)
    points = calibration.fit_smooth_isotonic(raw_2025, table.loc[year, "y_any"].to_numpy())
    frame = table.loc[test, ["object", "day", "y_any"]].reset_index(drop=True)
    frame["raw"] = combine(ptest)
    frame["probability"] = np.clip(calibration.apply_points(points, frame["raw"]), 0, 1)
    frame["index"] = np.clip(np.rint(100 * (1 - frame["probability"])), 0, 100).astype(int)
    window = frame.loc[(frame["day"] >= TEST_START) & (frame["day"] <= TEST_END)]
    target = window["y_any"].to_numpy()
    report = {
        "target": "хотя бы один инцидент реестра на объекте за сутки: отключение питания, подтопление или пожарный",
        "calibration": "сглаженная изотоническая по 2025 году на вероятностях моделей объекта, обученных до 2025",
        "period": "2026H1",
        "objects": int(window["object"].nunique()),
        "new_index": {**quality(target, window["probability"].to_numpy()), **ties(window, "index")},
        "independent_product": quality(target, np.clip(window["raw"].to_numpy(), 0, 1)),
    }
    if os.path.exists(HISTORY):
        stored = json.load(open(HISTORY, encoding="utf-8"))
        old = stored.get("objects_channels", stored["objects"])
        rows = [(str(obj), pd.Timestamp(day), value) for obj, series in old.items() for day, value in series]
        old = pd.DataFrame(rows, columns=["object", "day", "old_index"])
        both = window.merge(old, on=["object", "day"])
        both["old_probability"] = 1 - both["old_index"] / 100
        report["same_object_days"] = {
            "rows": int(len(both)),
            "objects": int(both["object"].nunique()),
            "new_index": {**quality(both["y_any"].to_numpy(), both["probability"].to_numpy()), **ties(both, "index")},
            "old_index": {**quality(both["y_any"].to_numpy(), both["old_probability"].to_numpy()), **ties(both, "old_index")},
        }
    new, old = report["new_index"], report.get("same_object_days", {})
    better = (new["ece"] <= 0.03 and (not old or (old["new_index"]["avg_precision"] >= old["old_index"]["avg_precision"]
                                                  and old["new_index"]["top_value_share"] < old["old_index"]["top_value_share"])))
    report["decision"] = "в прод" if better else "в таблицу проверенных подходов"
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(json.dumps({k: report[k] for k in ("new_index", "decision")}, ensure_ascii=False))
    if old:
        log(json.dumps(report["same_object_days"], ensure_ascii=False))
    if not better:
        return
    os.makedirs(artifacts.artifact_dir(NAME), exist_ok=True)
    with open(os.path.join(artifacts.artifact_dir(NAME), "points.json"), "w", encoding="utf-8") as handle:
        json.dump({"raw_risk": [round(float(x), 6) for x in points[0]], "risk": [round(float(y), 6) for y in points[1]]}, handle)
    meta = {"model_config": {"label": "Индекс здоровья объекта", "target": report["target"], "kinds": list(object_risk.KINDS),
                             "calibration": {"method": "smooth_isotonic", "fit_period": "2025"}},
            "metrics_snapshot": {"test_2026h1": new}, "version": time.strftime("%Y-%m-%d")}
    with open(os.path.join(artifacts.artifact_dir(NAME), "meta.json"), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=1)
    history = json.load(open(HISTORY, encoding="utf-8")) if os.path.exists(HISTORY) else {"sections": {}}
    history.setdefault("objects_channels", history.get("objects", {}))
    history["objects"] = {str(obj): [[day.date().isoformat(), int(value)] for day, value in zip(part["day"], part["index"], strict=True)]
                          for obj, part in frame.sort_values("day").groupby("object")}
    history["period"] = f"{HISTORY_START.date()} — {HISTORY_END.date()}"
    history["basis"] = "objects: object incident models, calibrated union of power, flood and fire; sections: production channel models"
    with open(HISTORY, "w", encoding="utf-8") as handle:
        json.dump(history, handle, ensure_ascii=False, separators=(",", ":"))
    log(f"{NAME} сохранён, история объектов пересчитана: {len(history['objects'])} объектов")


if __name__ == "__main__":
    main()
