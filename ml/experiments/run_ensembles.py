import json
import os
import sys
import time

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from pipeline import artifacts, evaluate, recipes
from pipeline.formal import metrics as fm
from run_refit_study import current_window, frames, training_rows

OUTPUT = os.path.join(os.path.dirname(__file__), "ensembles.json")
MEMBERS = ("catboost", "lightgbm", "logistic_regression")
ENSEMBLES = {
    "catboost+lightgbm": ("catboost", "lightgbm"),
    "catboost+lightgbm+logreg": MEMBERS,
    "catboost+logreg": ("catboost", "logistic_regression"),
}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5,))
    return {"avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "top5_per_day": top["precision_top5_per_day"]}


def rank_mean(scores):
    return np.mean([rankdata(score) / len(score) for score in scores], axis=0)


def main() -> None:
    names = sys.argv[1:] or ["pump_24h", "pump_72h", "fan_24h", "fan_72h", "smoke_24h", "flood_24h", "phase_24h"]
    report = json.load(open(OUTPUT, encoding="utf-8")) if os.path.exists(OUTPUT) else {}
    for name, frame, horizon in frames(names):
        meta = artifacts.load_artifact(name)[1]
        columns, window = meta["feature_columns"], current_window(meta)
        frame = frame.reset_index(drop=True)
        year = frame["ts"].dt.year
        result = {"window": window, "production": recipes.recipe_of(meta)}
        for period, before, test in (("2025", 2025, year == 2025),
                                     ("2026H1", 2026, (year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon)))):
            train = training_rows(frame, before, window).to_numpy()
            test = test.to_numpy()
            y, ts = frame.loc[test, "target"].to_numpy(), frame.loc[test, "ts"].to_numpy()
            scores = {member: recipes.fit(member, frame.loc[train, columns], frame.loc[train, "target"]).predict_proba(frame.loc[test, columns])
                      for member in MEMBERS}
            for member, score in scores.items():
                result[f"{period}_{member}"] = summary(y, score, ts)
            for ensemble, members in ENSEMBLES.items():
                result[f"{period}_{ensemble}"] = summary(y, rank_mean([scores[m] for m in members]), ts)
            log(f"{name} {period}: " + ", ".join(f"{k.split('_', 1)[1]} {v['avg_precision']}" for k, v in result.items() if k.startswith(period)))
        candidates = [*MEMBERS, *ENSEMBLES]
        best = max(candidates, key=lambda key: result[f"2025_{key}"]["avg_precision"])
        result["selected_on_2025"] = best
        result["selected_2026H1"] = result[f"2026H1_{best}"]
        report[name] = result
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)


if __name__ == "__main__":
    main()
