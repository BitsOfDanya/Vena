"""Audit the selected pump blend across 2025 quarters and trigger types."""

import json

import pandas as pd
from sklearn.metrics import average_precision_score

from experiments.common import emit
from experiments.run_blend_experiment import fit_scores
from pipeline.extract import extract_events
from pipeline.formal.metrics import eval_at_threshold
from pipeline.models import LogisticRegressionModel
from pipeline.training import feature_columns


def threshold_from(path, variant):
    """Read a development-year threshold from an aggregate record."""
    with open(path, encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            if record.get("variant", record.get("linear_weight")) == variant:
                return record["threshold_p70"]
    raise ValueError(f"missing threshold for {variant}")


def score_baseline(frame, valid_frame):
    """Fit the original full-history logistic model with a 168h embargo."""
    train = frame["ts"] < pd.Timestamp("2025-01-01") - pd.Timedelta(hours=168)
    columns = feature_columns()
    model = LogisticRegressionModel().fit(
        frame.loc[train, columns], frame.loc[train, "target"],
    )
    return model.predict_proba(valid_frame[columns])


def report_slices(valid_frame, baseline, blend, baseline_threshold, blend_threshold):
    """Emit aggregate ranking and frozen-threshold metrics by known slice."""
    groups = {
        "quarter": valid_frame["ts"].dt.quarter.astype(str),
        "trigger": valid_frame["trigger"],
        "channel_history": valid_frame["channel_history"],
    }
    for group_name, values in groups.items():
        for group_value in sorted(values.unique()):
            mask = (values == group_value).to_numpy()
            labels = valid_frame.loc[mask, "target"].to_numpy()
            if labels.sum() < 100:
                continue
            result = {
                "group": group_name, "value": group_value,
                "n_valid": len(labels), "n_positive": int(labels.sum()),
                "baseline_ap": average_precision_score(labels, baseline[mask]),
                "blend_ap": average_precision_score(labels, blend[mask]),
                "baseline_frozen": eval_at_threshold(
                    labels, baseline[mask], baseline_threshold,
                ),
                "blend_frozen": eval_at_threshold(
                    labels, blend[mask], blend_threshold,
                ),
            }
            if group_name == "channel_history":
                result["median_history_days"] = float(
                    valid_frame.loc[mask, "history_days"].median()
                )
            emit(result)


def main():
    """Reproduce one 2025 diagnostic audit without model selection."""
    frame = pd.read_parquet("analysis/ml_ready/pump72_features.parquet")
    valid_frame, (linear, tree), _ = fit_scores(frame, 2025)
    trained_channels = set(
        frame.loc[
            frame["ts"] < pd.Timestamp("2025-01-01") - pd.Timedelta(hours=168),
            "channel_id",
        ]
    )
    valid_frame = valid_frame.copy()
    valid_frame["channel_history"] = valid_frame["channel_id"].isin(trained_channels).map(
        {True: "seen", False: "new"},
    )
    events = extract_events("Состояние насоса")
    first_event = events.groupby("channel_id", observed=True)["ts"].min()
    valid_frame["history_days"] = (
        valid_frame["ts"] - valid_frame["channel_id"].map(first_event)
    ).dt.total_seconds() / 86400
    baseline = score_baseline(frame, valid_frame)
    blend = 0.5 * linear + 0.5 * tree
    baseline_threshold = threshold_from("experiments/pump_lr_dev_2024.jsonl", "baseline")
    blend_threshold = threshold_from("experiments/pump_blend_dev_2024.jsonl", 0.5)
    report_slices(valid_frame, baseline, blend, baseline_threshold, blend_threshold)


if __name__ == "__main__":
    main()
