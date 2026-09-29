import time

import pandas as pd

from experiments.common import (
    load_frozen,
    model_parser,
    report_variant,
    threshold_at_precision,
    validation_mask,
)
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.formal.metrics import frontier_metrics, pick_threshold
from pipeline.models import LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel


def fit_models(frame, year, window_years=3):
    valid_start = pd.Timestamp(f"{year}-01-01")
    train = frame["ts"] < valid_start - pd.Timedelta(hours=168)
    if window_years:
        train &= frame["ts"].dt.year >= year - window_years
    cols = training.feature_columns()
    x_train = frame.loc[train, cols]
    y_train = frame.loc[train, "target"]
    linear = LogisticRegressionModel().fit(x_train, y_train)
    tree = LightGBMModel({"num_leaves": 7, "min_child_samples": 500}).fit(x_train, y_train)
    return linear, tree


def fit_scores(frame, year, window_years=3):
    valid = validation_mask(frame, year)
    started = time.monotonic()
    linear, tree = fit_models(frame, year, window_years)
    x_valid = frame.loc[valid, training.feature_columns()]
    scores = (linear.predict_proba(x_valid), tree.predict_proba(x_valid))
    return frame.loc[valid], scores, round(time.monotonic() - started, 1)


def evaluate_blend(y, score, weight):
    result = frontier_metrics(y, score)
    result.update({
        "linear_weight": weight,
        "threshold_min_gap": pick_threshold(y, score),
        "threshold_p70": threshold_at_precision(y, score),
    })
    return result


def main():
    parser = model_parser()
    parser.add_argument("--sensor", choices=("pump", "fan"), default="pump")
    parser.add_argument("--window-years", type=int, choices=(0, 1, 2, 3, 4), default=3)
    parser.add_argument("--weights", default="0,0.25,0.5,0.75,1")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    valid_frame, (linear, tree), seconds = fit_scores(frame, args.valid_year, args.window_years)
    y = valid_frame["target"].to_numpy()
    frozen = load_frozen(args.frozen_from, "linear_weight")
    episodes = pd.read_parquet(episodes_cache) if args.operational else None

    for weight in map(float, args.weights.split(",")):
        score = weight * linear + (1 - weight) * tree
        result = evaluate_blend(y, score, weight)
        result.update({
            "sensor": args.sensor,
            "train_window_years": args.window_years,
            "valid_year": args.valid_year,
            "n_valid": len(y),
            "n_positive": int(y.sum()),
            "fit_score_seconds": seconds,
        })
        report_variant(result, frozen.get(weight), (y, score), valid_frame, episodes)


if __name__ == "__main__":
    main()
