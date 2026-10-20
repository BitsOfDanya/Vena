"""Fixed exploratory protocols. New diagnostic models are not VENA production models."""

import io
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from validation.evaluation import alert_metrics
from validation.external import FAILURES

SEED = 42
HGB_PARAMS = {
    "max_iter": 150,
    "max_leaf_nodes": 15,
    "l2_regularization": 1.0,
    "early_stopping": False,
    "random_state": SEED,
}


def binary_metrics(y, scores, threshold=0.5):
    y, scores = np.asarray(y), np.asarray(scores)
    prediction = scores >= threshold
    return {
        "rows": len(y),
        "positives": int(y.sum()),
        "positive_rate": float(y.mean()),
        "ap": float(average_precision_score(y, scores)) if y.sum() else None,
        "roc_auc": float(roc_auc_score(y, scores)) if len(np.unique(y)) == 2 else None,
        "threshold": float(threshold),
        "alerts": int(prediction.sum()),
        "precision": float(precision_score(y, prediction, zero_division=0))
        if prediction.any()
        else None,
        "recall": float(recall_score(y, prediction, zero_division=0))
        if y.sum()
        else None,
    }


def split_groups(groups):
    train, test = next(
        GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=SEED).split(
            np.zeros(len(groups)), groups=groups
        )
    )
    assert not set(np.asarray(groups)[train]) & set(np.asarray(groups)[test])
    return train, test


def hydraulic(root, output):
    folder = root / "hydraulic" / "raw"
    profile = pd.read_csv(
        folder / "profile.txt",
        sep="\t",
        header=None,
        names=["cooler", "valve", "pump", "accumulator", "unstable"],
    )
    # Only physical measurements, excluding virtual efficiency variables.
    sensors = [
        "PS1",
        "PS2",
        "PS3",
        "PS4",
        "PS5",
        "PS6",
        "EPS1",
        "FS1",
        "FS2",
        "TS1",
        "TS2",
        "TS3",
        "TS4",
        "VS1",
    ]
    columns = {}
    for sensor in sensors:
        values = np.loadtxt(folder / f"{sensor}.txt", dtype=np.float32)
        if len(values) != len(profile) or not np.isfinite(values).all():
            raise ValueError(f"Invalid cycle matrix: {sensor}")
        for name, stat in [
            ("mean", values.mean(axis=1)),
            ("std", values.std(axis=1)),
            ("min", values.min(axis=1)),
            ("max", values.max(axis=1)),
            ("delta", values[:, -1] - values[:, 0]),
        ]:
            columns[f"{sensor}_{name}"] = stat
    x = pd.DataFrame(columns)
    y = profile.pump.astype(int)
    # Entire nuisance operating configurations withheld, across all pump labels.
    groups = (
        profile[["cooler", "valve", "accumulator"]].astype(str).agg("/".join, axis=1)
    )
    train, test = split_groups(groups)
    model = HistGradientBoostingClassifier(**HGB_PARAMS).fit(
        x.iloc[train], y.iloc[train]
    )
    predictions = model.predict(x.iloc[test])
    majority = int(y.iloc[train].mode().iloc[0])
    metrics = {
        "accuracy": float(accuracy_score(y.iloc[test], predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y.iloc[test], predictions)),
        "macro_f1": float(f1_score(y.iloc[test], predictions, average="macro")),
        "majority_accuracy": float((y.iloc[test] == majority).mean()),
        "majority_balanced_accuracy": float(
            balanced_accuracy_score(y.iloc[test], np.full(len(test), majority))
        ),
        "confusion_labels": [0, 1, 2],
        "confusion_matrix": confusion_matrix(
            y.iloc[test], predictions, labels=[0, 1, 2]
        ).tolist(),
    }
    scored = profile.copy()
    scored["split"] = np.where(np.isin(np.arange(len(x)), train), "train", "test")
    scored["group"] = groups
    scored["prediction"] = np.nan
    scored.loc[test, "prediction"] = predictions
    scored.to_csv(output / "hydraulic_predictions.csv", index_label="cycle")
    joblib.dump(
        {"model": model, "features": list(x)}, output / "hydraulic_diagnostic.joblib"
    )
    return {
        "status": "completed",
        "model_role": "new diagnostic classifier, not production VENA",
        "task": "Current pump leakage severity 0/1/2 from a completed 60-second cycle",
        "rows": len(x),
        "features": len(x.columns),
        "train_rows": len(train),
        "test_rows": len(test),
        "train_groups": sorted(set(groups.iloc[train])),
        "test_groups": sorted(set(groups.iloc[test])),
        "metrics": metrics,
        "suitable_for": "Pump condition diagnosis from continuous sensors",
        "not_suitable_for": "24/72-hour failure forecasting: no real elapsed run-to-failure trajectory",
        "limitations": [
            "One experimental rig; unseen configurations are not unseen independent machines",
            "Summary uses the whole cycle, so inference happens after the cycle finishes",
        ],
    }


def water(root, output):
    frame = pd.read_csv(root / "water" / "water.csv")
    frame["timestamp"] = pd.to_datetime(frame.timestamp, format="%d-%m-%Y %H:%M")
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if frame.timestamp.duplicated().any() or not frame.fault_d7.isin([0, 1]).all():
        raise ValueError("Invalid water timestamps or target")
    boundary = pd.Timestamp("2022-10-01")
    train = frame.timestamp < boundary - pd.Timedelta(days=14)
    test = frame.timestamp >= boundary
    columns = [
        c
        for c in frame
        if c not in ("timestamp", "fault_d7") and frame.loc[train, c].notna().any()
    ]
    x, y = frame[columns], frame.fault_d7.astype(int)
    if y.loc[train].nunique() != 2 or not test.any():
        raise ValueError(
            "Fixed water split lacks training classes or test observations"
        )
    model = HistGradientBoostingClassifier(**HGB_PARAMS).fit(x.loc[train], y.loc[train])
    scores = model.predict_proba(x.loc[test])[:, 1]
    result = frame.loc[test, ["timestamp", "fault_d7"]].copy()
    result["score"] = scores
    result.to_csv(output / "water_predictions.csv", index=False)
    joblib.dump(
        {"model": model, "features": columns}, output / "water_diagnostic.joblib"
    )
    return {
        "status": "completed",
        "model_role": "new exploratory classifier, not production VENA",
        "task": "Classification of ±7-day leak proximity; not future failure prediction",
        "rows": len(frame),
        "features": columns,
        "missing_fraction": float(x.isna().mean().mean()),
        "train_rows": int(train.sum()),
        "test_rows": int(test.sum()),
        "train_end_exclusive": "2022-09-17",
        "test_start": "2022-10-01",
        "purge_days": 14,
        "train_positive_rate": float(y.loc[train].mean()),
        "metrics": binary_metrics(y.loc[test], scores),
        "suitable_for": "SCADA data quality, missingness, exploratory anomaly/leak-proximity classification",
        "not_suitable_for": "Validating causal early warning until exact leak onsets and feature provenance are supplied",
        "limitations": [
            "fault_d7 includes seven days AFTER leaks; no causal onset label",
            "Anomaly scores were precomputed upstream; their training windows are unknown",
            "Temporal purge does not repair potential leakage inside upstream features",
            "No event-level recall claimed: exact leak timestamps are absent",
        ],
    }


def smoke_file(path):
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    header = next(
        (i for i, line in enumerate(lines) if "Counter" in line and "Alarm?" in line),
        None,
    )
    if header is None:
        raise ValueError("Missing explicit Counter/Alarm? columns")
    frame = pd.read_csv(io.StringIO("\n".join(lines[header:])), sep="\t")
    frame.columns = frame.columns.str.strip()
    columns = ["Counter", "Alarm?", "Obscuration (%/ft)", "MIC(pA)", "CO"]
    frame = frame[columns].apply(pd.to_numeric, errors="coerce")
    if frame[["Counter", "Alarm?"]].isna().any().any():
        raise ValueError("Missing time or alarm label")
    if not frame.Counter.is_monotonic_increasing or frame.Counter.duplicated().any():
        raise ValueError("Non-increasing experiment clock")
    onset = frame.loc[frame["Alarm?"] > 0.5, "Counter"].min()
    # Use physical clock windows, not centered or future rolling calculations.
    signal = frame.set_index(pd.to_timedelta(frame.Counter, unit="s"))
    feature_columns = ["Obscuration (%/ft)", "MIC(pA)", "CO"]
    x = signal[feature_columns].copy()
    for column in feature_columns:
        x[column + "_mean10"] = signal[column].rolling("10s", min_periods=5).mean()
        x[column + "_std10"] = signal[column].rolling("10s", min_periods=5).std()
    x = x.reset_index(drop=True)
    # Avoid initial 5–10 second instrument-filter artifact documented by NIST.
    keep = (frame.Counter >= 10) & (frame.Counter <= frame.Counter.max() - 10)
    keep &= (frame.Counter < onset) if pd.notna(onset) else True
    keep &= frame.Counter % 5 == 0
    selected = x.loc[keep].copy()
    selected["target"] = (
        (onset > frame.loc[keep, "Counter"])
        & (onset <= frame.loc[keep, "Counter"] + 10)
    ).astype(int)
    selected["second"] = frame.loc[keep, "Counter"]
    selected["onset"] = onset
    selected["experiment"] = Path(path).stem
    selected["detector_model"] = Path(path).stem.split("-")[0]
    return selected


def nist_smoke(root, output):
    folder = root / "nist_smoke"
    files = sorted((folder / "smoke_box").rglob("*.tsv"))
    parts, rejected = [], []
    for path in files:
        try:
            part = smoke_file(path)
            if part.empty:
                rejected.append(
                    {"file": path.name, "reason": "No eligible pre-alarm samples"}
                )
            else:
                parts.append(part)
        except ValueError as exc:
            rejected.append({"file": path.name, "reason": str(exc)})
    data = pd.concat(parts, ignore_index=True)
    columns = [
        c
        for c in data
        if c not in {"target", "second", "onset", "experiment", "detector_model"}
    ]
    train, test = split_groups(data.detector_model)
    model = HistGradientBoostingClassifier(**HGB_PARAMS).fit(
        data.loc[train, columns], data.loc[train, "target"]
    )
    scores = model.predict_proba(data.loc[test, columns])[:, 1]
    scored = data.loc[
        test, ["experiment", "detector_model", "second", "onset", "target"]
    ].copy()
    scored["score"] = scores
    scored.to_csv(output / "nist_predictions.csv.gz", index=False)
    per_experiment = []
    for name, group in scored.groupby("experiment"):
        has_window = bool(group.target.any())
        hits = group.loc[(group.score >= 0.5) & (group.target == 1)]
        per_experiment.append(
            {
                "experiment": name,
                "has_observed_pre_alarm_window": has_window,
                "covered": bool(len(hits)),
                "any_false_window_alert": bool(
                    ((group.score >= 0.5) & (group.target == 0)).any()
                ),
                "lead_seconds": float((hits.onset - hits.second).max())
                if len(hits)
                else None,
            }
        )
    joblib.dump(
        {"model": model, "features": columns}, output / "nist_diagnostic.joblib"
    )
    return {
        "status": "completed",
        "model_role": "new diagnostic model, not VENA smoke_24h",
        "task": "First smoke-alarm activation in the next 10 seconds, using only pre-alarm measurements",
        "smoke_box_files": len(files),
        "used_files": data.experiment.nunique(),
        "room_files_downloaded_not_scored": len(list((folder / "room").rglob("*.tsv"))),
        "rejected_files": rejected,
        "features": columns,
        "train_rows": len(train),
        "test_rows": len(test),
        "train_detector_models": sorted(set(data.loc[train, "detector_model"])),
        "test_detector_models": sorted(set(data.loc[test, "detector_model"])),
        "metrics": binary_metrics(scored.target, scores),
        "test_experiments": len(per_experiment),
        "assessable_alarm_experiments": sum(
            e["has_observed_pre_alarm_window"] for e in per_experiment
        ),
        "covered_alarm_experiments": sum(e["covered"] for e in per_experiment),
        "experiments_with_false_window_alerts": sum(
            e["any_false_window_alert"] for e in per_experiment
        ),
        "per_experiment": per_experiment,
        "suitable_for": "Short-horizon sensor response and laboratory alarm-detection research",
        "not_suitable_for": "Predicting fire 24 hours ahead or determining field false-fire rates",
        "limitations": [
            "Alarm? is a manually activated latch, not a confirmed real-world fire label",
            "Alarm? and Microphone excluded from inputs; held-out detector models never enter training",
            "Room traces have no Alarm? onset column; require separate summary-table alignment",
            "This first exploration is not a safety certification or an unbiased field-performance estimate",
        ],
    }


def metro_analog_features(frame):
    signals = [
        "TP2",
        "TP3",
        "H1",
        "DV_pressure",
        "Reservoirs",
        "Motor_current",
        "Oil_temperature",
    ]
    hourly = (
        frame.set_index("timestamp")[signals]
        .resample("1h", closed="right", label="right")
        .mean()
    )
    # All windows end at t; keep gaps as NaN instead of filling from the future.
    x = hourly.add_suffix("_mean1h")
    x = x.join(hourly.rolling(6, min_periods=6).mean().add_suffix("_mean6h"))
    x = x.join(hourly.rolling(6, min_periods=6).std().add_suffix("_std6h"))
    return x


def metro_analog(root, output):
    csv_path = root / "metropt3" / "raw" / "MetroPT3(AirCompressor).csv"
    frame = pd.read_csv(csv_path, parse_dates=["timestamp"]).sort_values("timestamp")
    x = metro_analog_features(frame).dropna()
    train = x.index < "2020-03-01"
    model = IsolationForest(
        n_estimators=200, max_samples=256, random_state=SEED, n_jobs=1
    )
    model.fit(x.loc[train])
    threshold = float(np.quantile(-model.score_samples(x.loc[train]), 0.99))
    test = x.loc[(x.index >= "2020-04-01") & (x.index < "2020-08-01")]
    # Same 6-hour forecast grid as the frozen production model check.
    test = test.loc[test.index.hour % 6 == 0]
    score = -model.score_samples(test)
    truth = pd.DataFrame(
        [("metropt3/APU", pd.Timestamp(a), pd.Timestamp(b)) for a, b in FAILURES],
        columns=["channel_id", "episode_start", "episode_end"],
    )
    results, frames = {}, []
    for horizon in (24, 72):
        data = pd.DataFrame(
            {
                "channel_id": "metropt3/APU",
                "ts": test.index,
                "score": score,
                "alert": score >= threshold,
                "target": 0,
                "eligible": True,
                "horizon_hours": horizon,
            }
        )
        data = data.loc[
            data.ts + pd.Timedelta(hours=horizon)
            <= min(pd.Timestamp("2020-08-01"), frame.timestamp.max())
        ].copy()
        for event in truth.itertuples():
            data.loc[
                (data.ts < event.episode_start)
                & (data.ts + pd.Timedelta(hours=horizon) >= event.episode_start),
                "target",
            ] = 1
            data.loc[
                (data.ts >= event.episode_start) & (data.ts <= event.episode_end),
                "eligible",
            ] = False
        chosen = data.loc[data.eligible]
        results[str(horizon)] = {
            "metrics": binary_metrics(chosen.target, chosen.score, threshold),
            "operations": alert_metrics(data, truth),
        }
        frames.append(data)
    pd.concat(frames).to_csv(output / "metro_analog_predictions.csv", index=False)
    joblib.dump(
        {"model": model, "features": list(x), "threshold": threshold},
        output / "metro_analog_diagnostic.joblib",
    )
    return {
        "status": "completed",
        "model_role": "new unsupervised analog diagnostic, not production VENA",
        "task": "Does analog abnormality precede documented leaks within 24/72h?",
        "train_rows": int(train.sum()),
        "train_end_exclusive": "2020-03-01",
        "threshold_source": "99th percentile of training anomaly scores; no test tuning",
        "features": list(x),
        "results": results,
        "suitable_for": "Comparing analog anomaly detection with event-based failure forecasting",
        "limitations": [
            "Anomaly score is NOT a calibrated failure probability",
            "One compressor, four reported leaks; March excluded from scoring, not used for tuning",
            "Abnormality may reflect operating-mode changes rather than approaching failure",
        ],
    }


def metro_matched(output):
    """Compare existing scores at the same timestamps; no fitting or thresholds changed."""
    frozen = pd.read_csv(output / "external_predictions.csv.gz", parse_dates=["ts"])
    analog = pd.read_csv(output / "metro_analog_predictions.csv", parse_dates=["ts"])
    truth = pd.read_csv(
        output / "external_truth.csv", parse_dates=["episode_start", "episode_end"]
    )
    result = {"frozen": {}, "analog": {}, "coverage": {}}
    for horizon in (24, 72):
        name = f"pump_{horizon}h"
        source = frozen.loc[frozen.model == name]
        other = analog.loc[analog.horizon_hours == horizon].copy()
        selected = source.set_index("ts").loc[other.ts].reset_index()
        other = other.reset_index(drop=True)
        np.testing.assert_array_equal(selected.target, other.target)
        np.testing.assert_array_equal(selected.eligible, other.eligible)
        if selected.threshold_high.nunique() != 1:
            raise ValueError("Comparison expects one frozen threshold per model")
        valid = selected.loc[selected.eligible]
        result["frozen"][name] = {
            **binary_metrics(
                valid.target, valid.raw_score, selected.threshold_high.iloc[0]
            ),
            "operations": alert_metrics(selected, truth),
        }
        valid_other = other.loc[other.eligible]
        # Fixed threshold recorded by the fitted exploratory model.
        artifact = joblib.load(output / "metro_analog_diagnostic.joblib")
        result["analog"][str(horizon)] = {
            "metrics": binary_metrics(
                valid_other.target, valid_other.score, artifact["threshold"]
            ),
            "operations": alert_metrics(other, truth),
        }
        result["coverage"][str(horizon)] = {
            "frozen_grid_rows": len(source),
            "common_grid_rows": len(selected),
            "common_eligible_rows": len(valid),
            "omitted_without_complete_analog_history": len(source) - len(selected),
        }
    result["note"] = (
        "Analog model abstains without six complete hourly bins. Compare both models on the intersection, with identical ground truth and active-episode exclusions."
    )
    return result
