import json
import os
import sys
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, config
from run_object_level import MODELS, frames

OUTPUT = os.path.join(config.ROOT, "results", "threshold_curves.json")
QUANTILES = np.concatenate([np.linspace(0.5, 0.95, 10), np.linspace(0.96, 0.999, 14), [0.9995, 0.9999]])


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def point(test, threshold, calibrator, days):
    above = test["score"] >= threshold
    positives = int(test["target"].sum())
    flagged = test.loc[above]
    probability = float(np.clip(calibration.apply_isotonic(calibrator, [threshold])[0], 0, 1)) if calibrator is not None else None
    return {
        "threshold": round(float(threshold), 6),
        "probability": round(probability, 4) if probability is not None else None,
        "precision": round(float(flagged["target"].mean()), 4) if len(flagged) else None,
        "recall": round(float(flagged["target"].sum() / positives), 4) if positives else None,
        "channels_per_day": round(flagged.groupby(flagged["ts"].dt.normalize())["channel_id"].nunique().sum() / days, 2),
    }


def main():
    names = sys.argv[1:] or list(MODELS)
    report = {"period": "2026H1", "unit": "кандидат оценки канала; нагрузка — каналов с оценкой выше порога в сутки",
              "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "models": {}}
    for name, frame, horizon in frames(names):
        model, meta = artifacts.load_artifact(name)
        calibrator = artifacts.load_calibrator(name)
        test = frame.loc[frame["ts"].dt.year == 2026, ["channel_id", "ts", "target", *meta["feature_columns"]]]
        test = test[["channel_id", "ts", "target"]].assign(score=model.predict_proba(test[meta["feature_columns"]]))
        days = test["ts"].dt.normalize().nunique()
        grid = sorted(set(np.quantile(test["score"], QUANTILES)))
        current = meta["model_config"].get("risk_level_thresholds", {})
        report["models"][name] = {
            "label": MODELS[name][0], "horizon_hours": horizon, "base_rate": round(float(test["target"].mean()), 4),
            "candidates": int(len(test)), "days": int(days),
            "current": {level: point(test, value, calibrator, days) for level, value in current.items()},
            "curve": [point(test, value, calibrator, days) for value in grid],
        }
        log(f"{name}: " + ", ".join(f"{k} P {v['precision']} R {v['recall']} {v['channels_per_day']}/сут" for k, v in report["models"][name]["current"].items()))
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(f"written {OUTPUT}")


if __name__ == "__main__":
    main()
