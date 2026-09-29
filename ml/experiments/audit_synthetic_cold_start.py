import argparse
import json
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from pipeline import alerts as alerts_mod
from pipeline import candidates as candidates_mod
from pipeline import episodes as episodes_mod
from pipeline import features as features_mod
from pipeline import training
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

EVENT_CACHE = "analysis/ml_ready/cache/events_Состояние_насоса.parquet"
FEATURE_CACHE = "analysis/ml_ready/pump72_features.parquet"
SENSOR = "Состояние насоса"


def synthetic_first_month(events, held):
    start = pd.Timestamp("2024-01-01")
    end = pd.Timestamp("2024-02-01")
    selected = events.loc[events["channel_id"].isin(held) & (events["ts"] >= start)]
    episodes = episodes_mod.build_episodes(selected)
    candidates = candidates_mod.generate_candidates(selected, SENSOR)
    candidates = candidates.loc[(candidates["ts"] >= start) & (candidates["ts"] < end)]
    global_rates = features_mod.compute_global_rates(events, 2023)
    frame = features_mod.compute_features(
        candidates, selected, episodes, global_rates=global_rates,
    )
    frame = episodes_mod.assign_targets(frame, episodes, horizon_hours=72)
    return frame, episodes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--fraction", type=float, default=0.2)
    args = parser.parse_args()
    if not 0 < args.fraction < 1:
        raise ValueError("fraction must be between zero and one")
    tick = time.monotonic()
    frame = pd.read_parquet(FEATURE_CACHE)
    events = pd.read_parquet(EVENT_CACHE)
    channel_pool = np.sort(frame.loc[frame["ts"].dt.year == 2024, "channel_id"].unique())
    random = np.random.default_rng(args.seed)
    held = set(random.choice(channel_pool, round(len(channel_pool) * args.fraction), replace=False))
    train = (frame["ts"] < pd.Timestamp("2024-01-01") - pd.Timedelta(hours=168))
    train &= ~frame["channel_id"].isin(held)
    recent = train & (frame["ts"].dt.year >= 2021)
    valid, episodes = synthetic_first_month(events, held)
    columns = training.feature_columns()
    baseline = LogisticRegressionModel().fit(frame.loc[train, columns], frame.loc[train, "target"])
    linear = LogisticRegressionModel().fit(frame.loc[recent, columns], frame.loc[recent, "target"])
    tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(
        frame.loc[recent, columns], frame.loc[recent, "target"],
    )
    x_valid = valid[columns]
    baseline_score = baseline.predict_proba(x_valid)
    blend_score = 0.5 * (linear.predict_proba(x_valid) + tree.predict_proba(x_valid))
    labels = valid["target"].to_numpy()
    jan_episodes = episodes.loc[
        (episodes["episode_start"] >= pd.Timestamp("2024-01-01"))
        & (episodes["episode_start"] < pd.Timestamp("2024-02-01"))
    ]
    covered = alerts_mod.candidate_coverage(valid[["channel_id", "ts"]], jan_episodes, 72)
    result = {
        "year": 2024, "period": "first_month_after_history_reset",
        "seed": args.seed, "fraction_channels": args.fraction,
        "n_held_channels": len(held), "n_train": int(train.sum()),
        "n_recent_train": int(recent.sum()),
        "n_candidates": len(valid), "n_positive": int(labels.sum()),
        "n_episodes": len(jan_episodes),
        "n_covered_episodes": int(covered.sum()),
        "baseline_ap": float(average_precision_score(labels, baseline_score)),
        "blend_ap": float(average_precision_score(labels, blend_score)),
        "ap_gain": float(average_precision_score(labels, blend_score)
                         - average_precision_score(labels, baseline_score)),
        "seconds": round(time.monotonic() - tick, 1),
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
