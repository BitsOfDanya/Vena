"""Check whether stronger L2 regularization improves fan 72-hour ranking."""

import argparse
import time

import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from experiments.common import emit, validation_mask
from pipeline.formal.metrics import frontier_metrics
from pipeline.training import feature_columns


def prepare_arrays(frame, year):
    """Scale training features without using future rows."""
    valid_start = pd.Timestamp(f"{year}-01-01")
    train = frame["ts"] < valid_start - pd.Timedelta(hours=168)
    valid = validation_mask(frame, year)
    columns = feature_columns()
    scaler = StandardScaler()
    x_train = scaler.fit_transform(frame.loc[train, columns].fillna(-1))
    x_valid = scaler.transform(frame.loc[valid, columns].fillna(-1))
    y_train = frame.loc[train, "target"].to_numpy()
    y_valid = frame.loc[valid, "target"].to_numpy()
    return x_train, x_valid, y_train, y_valid


def main() -> None:
    """Fit fixed C values on a chronological fan holdout."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--c-values", default="0.01,0.1,1,10")
    parser.add_argument("--class-weight", choices=("balanced", "none"), default="balanced")
    args = parser.parse_args()

    frame = pd.read_parquet("analysis/ml_ready/fan72_features.parquet")
    x_train, x_valid, y_train, y_valid = prepare_arrays(frame, args.valid_year)

    for c_value in (float(value) for value in args.c_values.split(",")):
        started = time.monotonic()
        model = LogisticRegression(
            C=c_value,
            class_weight="balanced" if args.class_weight == "balanced" else None,
            max_iter=1000, random_state=42,
        )
        model.fit(x_train, y_train)
        score = model.predict_proba(x_valid)[:, 1]
        result = frontier_metrics(y_valid, score)
        result.update({
            "sensor": "fan",
            "variant": (
                f"l2_c_{c_value:g}" if args.class_weight == "balanced"
                else f"unweighted_l2_c_{c_value:g}"
            ),
            "valid_year": args.valid_year, "embargo_hours": 168,
            "n_train": len(y_train), "n_valid": len(y_valid),
            "n_positive": int(y_valid.sum()),
            "fit_score_seconds": round(time.monotonic() - started, 1),
        })
        emit(result)


if __name__ == "__main__":
    main()
