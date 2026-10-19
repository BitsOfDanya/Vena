import json
import os
import time

import pandas as pd

from pipeline import candidates as candidates_mod
from pipeline import config, episodes as episodes_mod, extract, features as features_mod, recipes, splits, states
from pipeline.formal import metrics as fm
from pipeline import evaluate

OUTPUT = os.path.join(os.path.dirname(__file__), "temp_sensor.json")
SENSOR = "Датчик температуры"
EMBARGO = pd.Timedelta(hours=168)
MIN_TOP5_PRECISION = 0.3


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def quality(frame, score):
    frontier = fm.frontier_metrics(frame["target"].to_numpy(), score)
    top = evaluate.evaluate_daily_topk_fixed(frame["ts"].to_numpy(), frame["target"].to_numpy(), score, counts=(5,))
    return {"n": int(len(frame)), "base_rate": round(float(frame["target"].mean()), 4),
            "avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "recall_at_precision_0.7": round(float(frontier["recall_at_precision_0.7"]), 4),
            "precision_top5_per_day": top["precision_top5_per_day"]}


def main():
    events = extract.extract_events(SENSOR)
    fault = states.technical_fault(events["raw_value"], events["alarm_flag"].map({1: "t", 0: "f"}), states.TEMPERATURE_LIMITS)
    report = {"target": "начало эпизода технической неисправности датчика температуры за 24 ч",
              "fault_records": int(fault.sum()), "text_fault_records": int((events["raw_value"] == config.FAULT_LITERAL).sum())}
    events = events.assign(raw_value=events["raw_value"].where(~fault, config.FAULT_LITERAL))
    episodes = episodes_mod.build_episodes(events)
    report["episodes"] = int(len(episodes))
    report["episodes_by_year"] = {str(k): int(v) for k, v in episodes["episode_start"].dt.year.value_counts().sort_index().items()}
    log(f"faults {report['fault_records']} episodes {report['episodes']}")
    candidates = candidates_mod.generate_candidates(events, SENSOR)
    rates = features_mod.compute_global_rates(events, config.TRAIN_YEARS[1])
    base = features_mod.compute_features(candidates, events, episodes, numeric_mode=True, duty_cycle_mode=False, global_rates=rates)
    frame = splits.assign_split(episodes_mod.assign_targets(base, episodes, 24))
    columns = [c for c in features_mod.FEATURE_COLUMNS if c in frame.columns]
    prior = "channel_failure_prior" if "channel_failure_prior" in frame.columns else None
    for name, (train_before, test_mask) in {
        "selection_2025": (pd.Timestamp("2025-01-01"), frame["ts"].dt.year == 2025),
        "test_2026h1": (pd.Timestamp("2026-01-01"), frame["ts"].dt.year == 2026),
    }.items():
        train = frame["ts"] < train_before - EMBARGO
        test = frame.loc[test_mask]
        report[name] = {}
        for recipe in ("catboost", "lightgbm", "logistic_regression"):
            model = recipes.fit(recipe, frame.loc[train, columns], frame.loc[train, "target"])
            report[name][recipe] = quality(test, model.predict_proba(test[columns]))
        if prior:
            report[name]["channel_prior"] = quality(test, test[prior].to_numpy())
        log(f"{name}: " + json.dumps({k: v["avg_precision"] for k, v in report[name].items()}))
    best = max(report["selection_2025"], key=lambda k: report["selection_2025"][k]["avg_precision"])
    report["selected_on_2025"] = best
    test = report["test_2026h1"][best]
    useful = test["avg_precision"] > 2 * test["base_rate"] and test["precision_top5_per_day"] >= MIN_TOP5_PRECISION
    report["decision"] = "в прод" if useful and best != "channel_prior" else "в таблицу проверенных подходов"
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(f"selected {best}: {report['test_2026h1'][best]} -> {report['decision']}")


if __name__ == "__main__":
    main()
