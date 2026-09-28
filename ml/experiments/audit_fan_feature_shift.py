"""Explain aggregate changes in fan logistic score scale."""

import argparse
import json

import numpy as np
import pandas as pd

from experiments.common import validation_mask
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.models import LogisticRegressionModel


def main():
    """Compare mean standardized feature contributions across time."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--valid-year", type=int, choices=(2025, 2026), required=True)
    args = parser.parse_args()
    cache, _, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache)
    start = pd.Timestamp(f"{args.valid_year}-01-01")
    train = frame["ts"] < start - pd.Timedelta(hours=168)
    valid = validation_mask(frame, args.valid_year)
    columns = training.feature_columns()
    x_train = frame.loc[train, columns].fillna(-1)
    x_valid = frame.loc[valid, columns].fillna(-1)
    model = LogisticRegressionModel().fit(x_train, frame.loc[train, "target"])
    score_train = model.predict_proba(x_train)
    score_valid = model.predict_proba(x_valid)
    mean_valid = x_valid.mean(axis=0).to_numpy()
    mean_train = model.scaler.mean_
    coefficient = model.model.coef_[0]
    delta_contribution = (mean_valid - mean_train) / model.scaler.scale_ * coefficient
    order = np.argsort(np.abs(delta_contribution))[::-1][:12]
    result = {
        "valid_year": args.valid_year,
        "n_train": int(train.sum()),
        "n_valid": int(valid.sum()),
        "train_target_rate": float(frame.loc[train, "target"].mean()),
        "valid_target_rate": float(frame.loc[valid, "target"].mean()),
        "train_score_median": float(np.median(score_train)),
        "valid_score_median": float(np.median(score_valid)),
        "train_score_p95": float(np.quantile(score_train, 0.95)),
        "valid_score_p95": float(np.quantile(score_valid, 0.95)),
        "mean_logit_delta": float(delta_contribution.sum()),
        "top_mean_logit_shifts": [
            {
                "feature": columns[index],
                "delta_contribution": float(delta_contribution[index]),
                "train_mean": float(mean_train[index]),
                "valid_mean": float(mean_valid[index]),
                "train_median": float(x_train.iloc[:, index].median()),
                "valid_median": float(x_valid.iloc[:, index].median()),
                "train_p95": float(x_train.iloc[:, index].quantile(0.95)),
                "valid_p95": float(x_valid.iloc[:, index].quantile(0.95)),
            }
            for index in order
        ],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
