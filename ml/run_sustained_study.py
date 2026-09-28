"""Sustained-fault target for pumps and fans.

More than half of the "Неисправен" episodes are a single event, which caps the
formal precision/recall target. This study relabels the 72-hour target with two
definitions of a lasting fault and compares, on the production split, the
current production model with a LightGBM trained on each new label:
- continuous: the channel stays in the fault state at least SUSTAINED_MINUTES;
- episode: the fault episode (repeats within 6 hours) spans at least SUSTAINED_MINUTES. Operational quality is the precision of the daily top 1% of
candidates. Results go to results/sustained_study.json.
"""

import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, config, episodes as episodes_mod, evaluate, experiments, training
from pipeline.formal import metrics as fm
from pipeline.targets import discovery
from pipeline.targets.model_zoo import LightGBMModel

HORIZON_HOURS = 72
SUSTAINED_MINUTES = 60
DEVICES = {"pump": "pump_72h", "fan": "fan_72h"}
OUTPUT = os.path.join(config.ROOT, "results", "sustained_study.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def quality(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    daily = evaluate.evaluate_daily_topk(ts, target, score)
    return {
        "base_rate": round(float(np.mean(target)), 4),
        "pr_auc": round(float(frontier["pr_auc"]), 4),
        "roc_auc": round(float(frontier["roc_auc"]), 4),
        "recall_at_precision_0.7": round(float(frontier["recall_at_precision_0.7"]), 4),
        "precision_at_recall_0.5": round(float(frontier["precision_at_recall_0.5"]), 4),
        "daily_top1pct_precision": daily.get("daily_precision_top_1pct"),
    }


def main() -> None:
    report = {"sustained_minutes": SUSTAINED_MINUTES, "horizon_hours": HORIZON_HOURS}
    columns = training.feature_columns()
    for device, production in DEVICES.items():
        ctx = experiments.DeviceContext(config.SENSOR_ALIASES[device])
        frame = ctx.build(horizon_hours=HORIZON_HOURS)
        span = (ctx.episodes["episode_end"] - ctx.episodes["episode_start"]).dt.total_seconds() / 60
        definitions = {
            "continuous": discovery.sustained_onsets(ctx.events, config.FAULT_LITERAL, SUSTAINED_MINUTES),
            "episode": ctx.episodes.loc[span >= SUSTAINED_MINUTES],
        }
        train = frame["split"] == "train"
        test = (frame["split"] == "test") & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=HORIZON_HOURS))
        ts = frame.loc[test, "ts"].values

        model, meta = artifacts.load_artifact(production)
        current = model.predict_proba(frame.loc[test, meta["feature_columns"]])
        report[device] = {
            "all_fault_episodes": int(len(ctx.episodes)),
            "current_model_on_any_fault": quality(frame.loc[test, "target"].values, current, ts),
        }
        for name, lasting in definitions.items():
            label = episodes_mod.assign_targets(frame[["channel_id", "ts"]], lasting, HORIZON_HOURS)["target"].values
            challenger = LightGBMModel({"n_estimators": 300, "num_leaves": 31, "min_child_samples": 200})
            challenger.fit(frame.loc[train, columns], label[train.values])
            report[device][name] = {
                "episodes": int(len(lasting)),
                "current_model": quality(label[test.values], current, ts),
                "relabeled_model": quality(label[test.values], challenger.predict_proba(frame.loc[test, columns]), ts),
            }
        log(f"{device}: {json.dumps(report[device], ensure_ascii=False)}")

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
