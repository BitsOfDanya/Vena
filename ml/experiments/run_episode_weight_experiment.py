import argparse
import time

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import frontier_metrics


def positive_episode_weights(train_frame, episodes, strength):
    y = train_frame["target"].to_numpy()
    weights = np.ones(len(train_frame), dtype=float)
    if strength == 0:
        return weights
    episode_id = np.full(len(train_frame), -1, dtype=np.int64)
    ts = train_frame["ts"].to_numpy()
    channel = train_frame["channel_id"].to_numpy()
    for cid, group in episodes.groupby("channel_id", observed=True):
        mask = (channel == cid) & (y == 1)
        if not mask.any():
            continue
        starts = group["episode_start"].to_numpy()
        ix = np.searchsorted(starts, ts[mask], side="right")
        valid = ix < len(starts)
        positions = np.flatnonzero(mask)
        episode_id[positions[valid]] = group.index.to_numpy()[ix[valid]]
    positive = y == 1
    if (episode_id[positive] < 0).any():
        raise ValueError("Positive training candidate without a future episode")
    _, inverse, counts = np.unique(episode_id[positive], return_inverse=True, return_counts=True)
    raw = counts[inverse].astype(float) ** (-strength)
    weights[positive] = raw / raw.mean()
    return weights


def fit_scores(train_frame, valid_frame, weights):
    columns = training.feature_columns()
    x_train = train_frame[columns].fillna(-1)
    x_valid = valid_frame[columns].fillna(-1)
    y_train = train_frame["target"].to_numpy()
    scaler = StandardScaler()
    scaled_train = scaler.fit_transform(x_train)
    scaled_valid = scaler.transform(x_valid)
    linear = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    linear.fit(scaled_train, y_train, sample_weight=weights)
    tree = LGBMClassifier(
        n_estimators=300, learning_rate=0.08, num_leaves=7, min_child_samples=500,
        subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
        class_weight="balanced", random_state=42, n_jobs=6, verbose=-1,
    )
    tree.fit(x_train, y_train, sample_weight=weights)
    return 0.5 * (linear.predict_proba(scaled_valid)[:, 1] + tree.predict_proba(x_valid)[:, 1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--strengths", default="0,0.5,1")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train].reset_index(drop=True)
    valid_frame = frame.loc[valid].reset_index(drop=True)
    y_valid = valid_frame["target"].to_numpy()
    for strength in map(float, args.strengths.split(",")):
        tick = time.monotonic()
        weights = positive_episode_weights(train_frame, episodes, strength)
        score = fit_scores(train_frame, valid_frame, weights)
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "variant": "equal_episode_weight", "strength": strength,
            "valid_year": args.valid_year, "n_train": len(train_frame),
            "n_valid": len(valid_frame), "n_positive": int(y_valid.sum()),
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "seconds": round(time.monotonic() - tick, 1),
        })
        emit(metrics)


if __name__ == "__main__":
    main()
