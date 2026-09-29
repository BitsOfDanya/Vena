import argparse
import time

import numpy as np
import pandas as pd
from scipy.special import expit, logit

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_blend_experiment import fit_models
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import frontier_metrics


def centered_scores(train_frame, valid_frame, models, strengths):
    linear, tree = models
    columns = training.feature_columns()
    train_score = (
        linear.predict_proba(train_frame[columns])
        + tree.predict_proba(train_frame[columns])
    ) / 2
    valid_score = (
        linear.predict_proba(valid_frame[columns])
        + tree.predict_proba(valid_frame[columns])
    ) / 2
    channel_medians = pd.Series(train_score, index=train_frame.index).groupby(
        train_frame["channel_id"], observed=True,
    ).median()
    global_median = float(np.median(train_score))
    valid_medians = valid_frame["channel_id"].map(channel_medians).fillna(global_median).to_numpy()
    safe_score = np.clip(valid_score, 1e-6, 1 - 1e-6)
    safe_median = np.clip(valid_medians, 1e-6, 1 - 1e-6)
    global_logit = logit(np.clip(global_median, 1e-6, 1 - 1e-6))
    delta = logit(safe_median) - global_logit
    return {strength: expit(logit(safe_score) - strength * delta) for strength in strengths}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--strengths", default="0,0.25,0.5,1")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = (frame["ts"] < start - pd.Timedelta(hours=168)) & (frame["ts"].dt.year >= args.valid_year - 3)
    valid = validation_mask(frame, args.valid_year)
    train_frame = frame.loc[train]
    valid_frame = frame.loc[valid]
    tick = time.monotonic()
    models = fit_models(frame, args.valid_year, 3)
    strengths = [float(value) for value in args.strengths.split(",")]
    scores = centered_scores(train_frame, valid_frame, models, strengths)
    fit_seconds = round(time.monotonic() - tick, 1)
    y_valid = valid_frame["target"].to_numpy()
    for strength, score in scores.items():
        metrics = frontier_metrics(y_valid, score)
        metrics.update({
            "strength": strength, "valid_year": args.valid_year,
            "n_train": len(train_frame), "n_valid": len(valid_frame),
            "n_positive": int(y_valid.sum()),
            "n_candidates_new_channel": int(
                (~valid_frame["channel_id"].isin(train_frame["channel_id"])).sum()
            ),
            "threshold_p70": threshold_at_precision(y_valid, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "fit_score_seconds": fit_seconds,
        })
        emit(metrics)


if __name__ == "__main__":
    main()
