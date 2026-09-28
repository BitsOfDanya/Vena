"""Compare temporal training policies for equipment 72-hour targets.

The feature cache and all model scores stay in ignored ``analysis/``. This
script prints only aggregate metrics, so no journal rows enter Git.
"""

import argparse
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from experiments.common import (
    add_frozen_metrics,
    emit,
    load_frozen,
    operational_summary,
    threshold_at_precision,
    validation_mask,
)
from pipeline import episodes as episodes_mod
from pipeline import training
from pipeline.formal.metrics import eval_at_threshold, frontier_metrics, pick_threshold
from pipeline.run import build_dataset

SENSOR_TYPES = {"pump": "Состояние насоса", "fan": "Состояние вентилятора"}
CALENDAR_COLUMNS = {
    "weekday", "hour", "month", "is_weekend", "hour_sin", "hour_cos",
    "weekday_sin", "weekday_cos",
}
VARIANTS = (
    "baseline", "recent_4y", "recent_3y", "recent_2y", "recent_1y",
    "decay_2y", "no_calendar",
    "baseline_near_4", "recent_3y_near_2", "recent_3y_near_4",
)


def cache_paths(sensor: str, with_duty_cycle: bool) -> tuple[Path, Path, Path]:
    """Return ignored feature, episode and near-label cache locations."""
    prefix = Path("analysis/ml_ready") / f"{sensor}72"
    suffix = "_duty_features.parquet" if with_duty_cycle else "_features.parquet"
    return (
        Path(f"{prefix}{suffix}"),
        Path(f"{prefix}_episodes.parquet"),
        Path(f"{prefix}_y168.parquet"),
    )


def prepare(cache: Path, episodes_cache: Path, sensor: str, with_duty_cycle: bool) -> None:
    """Build the causal feature cache once from the private local dataset."""
    if cache.exists():
        return
    cache.parent.mkdir(parents=True, exist_ok=True)
    frame, episodes = build_dataset(SENSOR_TYPES[sensor], 72, with_duty_cycle=with_duty_cycle)
    frame.to_parquet(cache, index=False)
    if not episodes_cache.exists():
        episodes.to_parquet(episodes_cache, index=False)


def prepare_near(frame: pd.DataFrame, episodes_cache: Path, near_cache: Path) -> np.ndarray:
    """Cache labels for events occurring within 168 hours after a candidate."""
    if not near_cache.exists():
        episodes = pd.read_parquet(episodes_cache)
        labeled = episodes_mod.assign_targets(
            frame[["channel_id", "ts"]], episodes, horizon_hours=168,
        )
        labeled[["target"]].to_parquet(near_cache, index=False)
    labels = pd.read_parquet(near_cache)["target"].to_numpy()
    if len(labels) != len(frame):
        raise ValueError("near-label cache does not match feature rows")
    return labels


def select_training_rows(frame, valid_year, variant, embargo_hours):
    """Apply a chronological holdout, embargo and optional trailing window."""
    valid_start = pd.Timestamp(f"{valid_year}-01-01")
    train_mask = frame["ts"] < valid_start - pd.Timedelta(hours=embargo_hours)
    if variant.startswith("recent_"):
        years = int(variant.split("_")[1].removesuffix("y"))
        train_mask &= frame["ts"].dt.year >= valid_year - years
    elif variant not in VARIANTS:
        raise ValueError(variant)
    return train_mask


def variant_weights(frame, train_mask, variant, valid_year, embargo_hours):
    """Weight recent rows or near misses using training-period labels only."""
    if variant == "decay_2y":
        valid_start = pd.Timestamp(f"{valid_year}-01-01")
        age_days = (
            valid_start - frame.loc[train_mask, "ts"]
        ).dt.total_seconds().to_numpy() / 86400
        weights = np.exp(-math.log(2) * age_days / 730.5)
        return weights / weights.mean()
    if "_near_" in variant:
        if embargo_hours < 168:
            raise ValueError("near-label weighting requires a 168h embargo")
        weight = int(variant.rsplit("_", 1)[1])
        y_train = frame.loc[train_mask, "target"].to_numpy()
        near = (frame.loc[train_mask, "y168"].to_numpy() == 1) & (y_train == 0)
        return np.where(near, weight, 1.0)
    return None


def predict_linear(frame, train_mask, valid_mask, cols, weights):
    """Fit the repository's baseline logistic model and score the holdout."""
    scaler = StandardScaler()
    x_train = scaler.fit_transform(frame.loc[train_mask, cols].fillna(-1))
    x_valid = scaler.transform(frame.loc[valid_mask, cols].fillna(-1))
    model = LogisticRegression(
        class_weight="balanced", max_iter=1000, random_state=42,
    )
    started = time.monotonic()
    model.fit(x_train, frame.loc[train_mask, "target"].to_numpy(), sample_weight=weights)
    score = model.predict_proba(x_valid)[:, 1]
    return score, round(time.monotonic() - started, 1)


def fit_and_score(
    frame: pd.DataFrame, valid_year: int, variant: str,
    embargo_hours: int = 168, with_duty_cycle: bool = False,
) -> tuple[dict, np.ndarray]:
    """Fit a temporal policy and score one future calendar year."""
    train_mask = select_training_rows(frame, valid_year, variant, embargo_hours)
    valid_mask = validation_mask(frame, valid_year)
    cols = training.feature_columns(with_duty_cycle=with_duty_cycle)
    if variant == "no_calendar":
        cols = [col for col in cols if col not in CALENDAR_COLUMNS]
    y_valid = frame.loc[valid_mask, "target"].to_numpy()
    weights = variant_weights(frame, train_mask, variant, valid_year, embargo_hours)
    score, seconds = predict_linear(frame, train_mask, valid_mask, cols, weights)
    metrics = frontier_metrics(y_valid, score)
    threshold = pick_threshold(y_valid, score)
    p70_threshold = threshold_at_precision(y_valid, score)
    metrics.update({
        "valid_year": valid_year,
        "variant": variant,
        "duty_cycle": with_duty_cycle,
        "embargo_hours": embargo_hours,
        "n_train": int(train_mask.sum()),
        "n_valid": int(valid_mask.sum()),
        "n_positive": int(y_valid.sum()),
        "threshold_min_gap": threshold,
        "at_threshold": eval_at_threshold(y_valid, score, threshold),
        "threshold_p70": p70_threshold,
        "at_p70": (
            eval_at_threshold(y_valid, score, p70_threshold)
            if p70_threshold is not None else None
        ),
        "fit_score_seconds": seconds,
    })
    return metrics, score


def main() -> None:
    """Run optional feature preparation and the requested model variants."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--sensor", choices=tuple(SENSOR_TYPES), default="pump")
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026))
    parser.add_argument("--variants", default=",".join(VARIANTS))
    parser.add_argument("--embargo-hours", type=int, default=168)
    parser.add_argument("--duty-cycle", action="store_true")
    parser.add_argument("--frozen-from")
    parser.add_argument("--operational", action="store_true")
    args = parser.parse_args()
    cache, episodes_cache, near_cache = cache_paths(args.sensor, args.duty_cycle)
    if args.prepare:
        prepare(cache, episodes_cache, args.sensor, args.duty_cycle)
    if args.valid_year is None:
        return
    frame = pd.read_parquet(cache)
    frozen = load_frozen(args.frozen_from, "variant")
    if args.operational:
        episodes = pd.read_parquet(episodes_cache)
    if "_near_" in args.variants:
        frame["y168"] = prepare_near(frame, episodes_cache, near_cache)
    valid_frame = frame.loc[validation_mask(frame, args.valid_year)]
    y_valid = valid_frame["target"].to_numpy()
    for variant in args.variants.split(","):
        result, score = fit_and_score(
            frame, args.valid_year, variant, args.embargo_hours, args.duty_cycle,
        )
        result["sensor"] = args.sensor
        if frozen:
            add_frozen_metrics(result, frozen[variant], y_valid, score)
        if args.operational:
            result["operational"] = operational_summary(valid_frame, score, episodes)
        emit(result)


if __name__ == "__main__":
    main()
