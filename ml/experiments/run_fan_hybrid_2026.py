import json
import os
import time

import torch  # noqa: F401  isort: skip
import pandas as pd

from pipeline import artifacts, config, evaluate, experiments, recipes, training
from pipeline.formal import metrics as fm
from pipeline.sequence import experiment as seq_experiment, hybrid_train, train as train_mod
from pipeline.sequence.hybrid_dataset import HybridSequenceDataset
from pipeline.sequence.hybrid_experiment import WINNER_CONFIG
from pipeline.sequence.hybrid_features import compute_normalized_features
from pipeline.sequence.hybrid_model import HybridEventTransformer
from pipeline.sequence.index import EventIndex

HORIZON = 72
EMBARGO = pd.Timedelta(hours=168)
OUTPUT = os.path.join(os.path.dirname(__file__), "fan_hybrid_2026h1.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    daily = evaluate.evaluate_daily_topk(ts, target, score, k_fracs=[0.01])
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5, 10))
    return {"avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "daily_top1pct": daily.get("daily_precision_top_1pct"),
            "top5_per_day": top["precision_top5_per_day"], "top10_per_day": top["precision_top10_per_day"]}


def main() -> None:
    ctx = experiments.DeviceContext(config.SENSOR_ALIASES["fan"])
    cand = ctx.build(horizon_hours=HORIZON).reset_index(drop=True)
    columns = training.feature_columns()
    index = EventIndex(ctx.events)
    year = cand["ts"].dt.year
    train = (cand["ts"] < pd.Timestamp("2025-01-01") - EMBARGO).values
    valid = (year == 2025).values
    recent = ((year == 2026) & (cand["ts"] <= cand["ts"].max() - pd.Timedelta(hours=HORIZON))).values
    channels = cand["channel_id"].astype(str).values
    ts_sec = cand["ts"].values.astype("datetime64[s]").astype("int64")
    target = cand["target"].values

    x_norm, feature_names, _, _ = compute_normalized_features(cand, train, feature_cols=columns)
    datasets = {name: HybridSequenceDataset(index, channels[mask], ts_sec[mask], target[mask], x_norm[mask], 128)
                for name, mask in (("train", train), ("valid", valid), ("recent", recent))}
    train_mod.set_seed(config.RANDOM_SEED)
    model = HybridEventTransformer(vocab_size=index.vocab_size, feature_dim=len(feature_names),
                                   d_model=128, nhead=4, num_layers=3)
    log(f"hybrid: train {int(train.sum())}, valid {int(valid.sum())}, recent {int(recent.sum())}")
    started = time.time()
    model, history, device = hybrid_train.fit(model, datasets["train"], datasets["valid"],
                                              seq_experiment.build_eval_fn(cand.loc[valid, "ts"].values),
                                              log_fn=log, seed=config.RANDOM_SEED, **WINNER_CONFIG)
    hybrid = hybrid_train.predict_scores(model, datasets["recent"], device)
    log(f"hybrid trained in {time.time() - started:.0f}s, {len(history)} epochs")

    catboost_2024 = recipes.fit("catboost", cand.loc[train, columns], target[train]).predict_proba(cand.loc[recent, columns])
    production = artifacts.load_artifact("fan_72h")[0].predict_proba(cand.loc[recent, columns])
    y, ts = target[recent], cand.loc[recent, "ts"].values
    report = {
        "period": "2026H1", "n": int(recent.sum()), "base_rate": round(float(y.mean()), 4),
        "hybrid_training_seconds": round(time.time() - started), "epochs": len(history),
        "hybrid_before_2025": summary(y, hybrid, ts),
        "catboost_before_2025": summary(y, catboost_2024, ts),
        "blend_before_2025": summary(y, 0.5 * catboost_2024 + 0.5 * hybrid, ts),
        "production_catboost_through_2025": summary(y, production, ts),
        "blend_production_and_hybrid": summary(y, 0.5 * production + 0.5 * hybrid, ts),
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    log(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
