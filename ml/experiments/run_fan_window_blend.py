import argparse
import time

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import (
    emit,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import frontier_metrics
from pipeline.models import LogisticRegressionModel


def half_aps(frame, score):
    h1 = frame["ts"].dt.month.to_numpy() <= 6
    labels = frame["target"].to_numpy()
    return {
        "h1": float(average_precision_score(labels[h1], score[h1])),
        "h2": float(average_precision_score(labels[~h1], score[~h1])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--recent-years", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--weights", default="0,0.25,0.5,0.75,1")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train_all = frame["ts"] < start - pd.Timedelta(hours=168)
    train_recent = train_all & (frame["ts"].dt.year >= args.valid_year - args.recent_years)
    valid = validation_mask(frame, args.valid_year)
    valid_frame = frame.loc[valid]
    columns = training.feature_columns()
    tick = time.monotonic()
    all_model = LogisticRegressionModel().fit(
        frame.loc[train_all, columns], frame.loc[train_all, "target"],
    )
    recent_model = LogisticRegressionModel().fit(
        frame.loc[train_recent, columns], frame.loc[train_recent, "target"],
    )
    score_all = all_model.predict_proba(valid_frame[columns])
    score_recent = recent_model.predict_proba(valid_frame[columns])
    fit_seconds = round(time.monotonic() - tick, 1)
    y = valid_frame["target"].to_numpy()
    for weight in map(float, args.weights.split(",")):
        score = (1 - weight) * score_all + weight * score_recent
        metrics = frontier_metrics(y, score)
        metrics.update({
            "sensor": "fan", "valid_year": args.valid_year,
            "weight_recent": weight, "recent_years": args.recent_years,
            "n_train_all": int(train_all.sum()),
            "n_train_recent": int(train_recent.sum()),
            "n_valid": len(y), "n_positive": int(y.sum()),
            "half_ap": half_aps(valid_frame, score),
            "threshold_p70": threshold_at_precision(y, score),
            "operational": operational_summary(valid_frame, score, episodes),
            "fit_score_seconds": fit_seconds,
        })
        emit(metrics)


if __name__ == "__main__":
    main()
