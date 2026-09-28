"""Shared, aggregate-only evaluation helpers for local ML experiments."""

import argparse
import json

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from pipeline.formal.metrics import eval_at_threshold
from pipeline.sequence.gate_eval import full_metrics


def validation_mask(frame, year, horizon_hours=72):
    """Keep only rows with an observable future target in the requested year."""
    valid = frame["ts"].dt.year == year
    if year == 2026:
        valid &= frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon_hours)
    return valid


def chronological_masks(frame, year, embargo_hours=168):
    """Keep training labels away from the next-year validation boundary."""
    start = pd.Timestamp(f"{year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=embargo_hours)
    return train, validation_mask(frame, year)


def threshold_at_precision(y, score, target_precision=0.70):
    """Return the threshold with best recall at the required precision."""
    precision, recall, thresholds = precision_recall_curve(y, score)
    qualifying = np.flatnonzero(precision[:-1] > target_precision)
    if qualifying.size == 0:
        return None
    best = qualifying[np.argmax(recall[qualifying])]
    return float(thresholds[best])


def load_frozen(path, key):
    """Load prior-year aggregate thresholds indexed by a variant key."""
    if not path:
        return {}
    with open(path, encoding="utf-8") as source:
        return {item[key]: item for item in map(json.loads, source)}


def add_frozen_metrics(result, prior, y, score):
    """Apply prior-year thresholds without retuning on the current year."""
    result["frozen_from_year"] = prior["valid_year"]
    result["at_frozen_min_gap"] = eval_at_threshold(
        y, score, prior["threshold_min_gap"],
    )
    if prior["threshold_p70"] is not None:
        result["at_frozen_p70"] = eval_at_threshold(
            y, score, prior["threshold_p70"],
        )


def operational_summary(valid_frame, score, episodes, horizon_hours=72):
    """Select the operational metrics used to compare model variants."""
    metrics = full_metrics(valid_frame, score, episodes, horizon_hours)
    keys = (
        "daily_precision_top_1pct", "alert_precision", "episode_recall",
        "median_lead_time_hours", "alerts_per_day", "episode_count",
    )
    return {key: metrics.get(key) for key in keys}


def emit(result):
    """Write one JSONL record containing no candidate-level data."""
    print(json.dumps(result, ensure_ascii=False, default=float), flush=True)


def model_parser():
    """Add the common chronological evaluation flags to a parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025, 2026), required=True)
    parser.add_argument("--frozen-from")
    parser.add_argument("--operational", action="store_true")
    return parser


def report_variant(result, prior, evaluation, valid_frame, episodes):
    """Apply optional prior-year and operational checks, then emit metrics."""
    y, score = evaluation
    if prior is not None:
        add_frozen_metrics(result, prior, y, score)
    if episodes is not None:
        result["operational"] = operational_summary(valid_frame, score, episodes)
    emit(result)
