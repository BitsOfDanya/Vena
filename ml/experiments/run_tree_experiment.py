"""Test fixed tree-model hypotheses on equipment 72-hour targets."""

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
from pipeline.models import CatBoostModel
from pipeline.targets.model_zoo import LightGBMModel

VARIANTS = {
    "all_lgbm": (None, "lgbm", {}),
    "all_lgbm_tiny": (None, "lgbm", {"num_leaves": 7, "min_child_samples": 500}),
    "recent1_lgbm_tiny": (1, "lgbm", {"num_leaves": 7, "min_child_samples": 500}),
    "recent1_lgbm_five": (1, "lgbm", {"num_leaves": 5, "min_child_samples": 750}),
    "recent3_lgbm": (3, "lgbm", {}),
    "recent3_lgbm_small": (3, "lgbm", {"num_leaves": 15, "min_child_samples": 200}),
    "recent3_lgbm_tiny": (3, "lgbm", {"num_leaves": 7, "min_child_samples": 500}),
    "recent3_lgbm_five": (3, "lgbm", {"num_leaves": 5, "min_child_samples": 750}),
    "recent3_lgbm_micro": (3, "lgbm", {"num_leaves": 3, "min_child_samples": 1000}),
    "recent3_lgbm_tiny_long": (
        3, "lgbm", {"num_leaves": 7, "min_child_samples": 500, "n_estimators": 600},
    ),
    "all_catboost": (None, "catboost", {}),
    "recent3_catboost": (3, "catboost", {}),
}


def run_one(frame, year, name, embargo_hours=168):
    """Fit a prespecified model and return only aggregate validation metrics."""
    window, family, params = VARIANTS[name]
    train = frame["ts"] < pd.Timestamp(f"{year}-01-01") - pd.Timedelta(hours=embargo_hours)
    if window is not None:
        train &= frame["ts"].dt.year >= year - window
    valid = validation_mask(frame, year)
    cols = training.feature_columns()
    y_valid = frame.loc[valid, "target"].to_numpy()

    model = LightGBMModel(params) if family == "lgbm" else CatBoostModel(params)
    started = time.monotonic()
    model.fit(frame.loc[train, cols], frame.loc[train, "target"].to_numpy())
    score = model.predict_proba(frame.loc[valid, cols])
    result = frontier_metrics(y_valid, score)
    result.update({
        "variant": name,
        "valid_year": year,
        "embargo_hours": embargo_hours,
        "n_train": int(train.sum()),
        "n_valid": int(valid.sum()),
        "n_positive": int(y_valid.sum()),
        "threshold_min_gap": pick_threshold(y_valid, score),
        "threshold_p70": threshold_at_precision(y_valid, score),
        "fit_score_seconds": round(time.monotonic() - started, 1),
    })
    return result, y_valid, score


def main():
    """Run a development year or a prespecified final-year check."""
    parser = model_parser()
    parser.add_argument("--sensor", choices=("pump", "fan"), default="pump")
    parser.add_argument("--variants", default=",".join(VARIANTS))
    args = parser.parse_args()

    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache)
    episodes = pd.read_parquet(episodes_cache) if args.operational else None
    frozen = load_frozen(args.frozen_from, "variant")
    valid_frame = frame.loc[validation_mask(frame, args.valid_year)]
    for name in args.variants.split(","):
        result, y_valid, score = run_one(frame, args.valid_year, name)
        result["sensor"] = args.sensor
        report_variant(result, frozen.get(name), (y_valid, score), valid_frame, episodes)


if __name__ == "__main__":
    main()
