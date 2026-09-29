import argparse
import time

import pandas as pd

from experiments.common import chronological_masks, emit
from pipeline.formal.metrics import frontier_metrics
from pipeline.models import LogisticRegressionModel
from pipeline.training import feature_columns

LONG_HISTORY = {
    "historical_failure_rate", "median_time_between_failures_days",
    "std_inter_failure_interval_days", "last_inter_failure_interval_days",
    "ratio_last_interval_to_historical_median", "days_since_last_2nd_failure",
    "days_since_last_3rd_failure", "channel_event_prior", "channel_alarm_prior",
    "channel_failure_prior",
}
FAILURE_HISTORY = LONG_HISTORY | {
    "failures_1d", "failures_3d", "failures_7d", "failures_14d",
    "failures_30d", "failures_90d", "time_since_last_failure_days",
    "ewma_failure_rate_7d", "ewma_failure_rate_30d",
}
DROP_SETS = {
    "baseline": set(),
    "no_long_history": LONG_HISTORY,
    "no_failure_history": FAILURE_HISTORY,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--variants", default=",".join(DROP_SETS))
    args = parser.parse_args()

    frame = pd.read_parquet("analysis/ml_ready/fan72_features.parquet")
    train, valid = chronological_masks(frame, args.valid_year)
    y_valid = frame.loc[valid, "target"].to_numpy()
    for variant in args.variants.split(","):
        columns = [col for col in feature_columns() if col not in DROP_SETS[variant]]
        started = time.monotonic()
        model = LogisticRegressionModel().fit(
            frame.loc[train, columns], frame.loc[train, "target"],
        )
        score = model.predict_proba(frame.loc[valid, columns])
        result = frontier_metrics(y_valid, score)
        result.update({
            "sensor": "fan", "variant": variant,
            "valid_year": args.valid_year, "embargo_hours": 168,
            "n_features": len(columns), "n_train": int(train.sum()),
            "n_valid": int(valid.sum()), "n_positive": int(y_valid.sum()),
            "fit_score_seconds": round(time.monotonic() - started, 1),
        })
        emit(result)


if __name__ == "__main__":
    main()
