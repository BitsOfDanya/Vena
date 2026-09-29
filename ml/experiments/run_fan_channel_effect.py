import argparse
import time

import pandas as pd
from scipy.sparse import csr_matrix, hstack
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from experiments.common import chronological_masks, emit
from pipeline.formal.metrics import frontier_metrics, pick_threshold
from pipeline.training import feature_columns


def design_matrices(frame, train, valid, use_channel):
    columns = feature_columns()
    scaler = StandardScaler()
    x_train = scaler.fit_transform(frame.loc[train, columns].fillna(-1))
    x_valid = scaler.transform(frame.loc[valid, columns].fillna(-1))
    if not use_channel:
        return x_train, x_valid

    encoder = OneHotEncoder(handle_unknown="ignore", dtype="float32")
    channel_train = encoder.fit_transform(frame.loc[train, ["channel_id"]])
    channel_valid = encoder.transform(frame.loc[valid, ["channel_id"]])
    return (
        hstack((csr_matrix(x_train), channel_train), format="csr"),
        hstack((csr_matrix(x_valid), channel_valid), format="csr"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2024, 2025), required=True)
    parser.add_argument("--with-channel", action="store_true")
    args = parser.parse_args()

    frame = pd.read_parquet("analysis/ml_ready/fan72_features.parquet")
    train, valid = chronological_masks(frame, args.valid_year)
    x_train, x_valid = design_matrices(frame, train, valid, args.with_channel)
    y_train = frame.loc[train, "target"].to_numpy()
    y_valid = frame.loc[valid, "target"].to_numpy()
    started = time.monotonic()
    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    model.fit(x_train, y_train)
    score = model.predict_proba(x_valid)[:, 1]
    result = frontier_metrics(y_valid, score)
    result.update({
        "sensor": "fan", "variant": "channel_effect" if args.with_channel else "baseline",
        "valid_year": args.valid_year, "embargo_hours": 168,
        "n_train": int(train.sum()), "n_valid": int(valid.sum()),
        "n_positive": int(y_valid.sum()),
        "threshold_min_gap": pick_threshold(y_valid, score),
        "fit_score_seconds": round(time.monotonic() - started, 1),
    })
    emit(result)


if __name__ == "__main__":
    main()
