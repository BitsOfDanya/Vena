import json
import os

import numpy as np
import pandas as pd

from pipeline import config, episodes as episodes_mod, features as features_mod, training
from pipeline.formal import metrics as fm
from pipeline.targets import model_zoo

DATA = os.path.join(config.ROOT, "external_datasets", "metropt3", "MetroPT3(AirCompressor).csv")
OUTPUT = os.path.join(config.ROOT, "results", "external", "metropt3_validation.json")

BINARY_SIGNALS = ["COMP", "DV_eletric", "Towers", "MPG", "LPS", "Pressure_switch", "Oil_level", "Caudal_impulses"]
ALARM_SIGNALS = {"LPS", "Oil_level"}
ANALOG_SIGNALS = ["TP2", "TP3", "Oil_temperature", "Motor_current", "DV_pressure", "H1"]
ANALOG_RESAMPLE = "1min"
LOW_QUANTILE = 0.1
HIGH_QUANTILE = 0.9

FAILURES = [
    ("2020-04-18 00:00", "2020-04-18 23:59"),
    ("2020-05-29 23:30", "2020-05-30 06:00"),
    ("2020-06-05 10:00", "2020-06-07 14:30"),
    ("2020-07-15 14:30", "2020-07-15 19:00"),
]

HORIZON_HOURS = 24
TRAIN_END = pd.Timestamp("2020-06-01")


def analog_events(frame, train_end):
    series = frame.set_index("timestamp")[ANALOG_SIGNALS].resample(ANALOG_RESAMPLE).mean().dropna(how="all")
    train = series.loc[series.index < train_end]
    parts = []
    for signal in ANALOG_SIGNALS:
        values = series[signal].dropna()
        if values.empty or train[signal].dropna().empty:
            continue
        low = train[signal].quantile(LOW_QUANTILE)
        high = train[signal].quantile(HIGH_QUANTILE)
        state = pd.Series("Норма", index=values.index)
        state[values > high] = "Высокий"
        state[values < low] = "Низкий"
        changed = state.ne(state.shift(1))
        changed.iloc[0] = True
        parts.append(
            pd.DataFrame(
                {
                    "channel_id": f"{signal}_band",
                    "ts": state.index[changed],
                    "raw_value": state[changed].values,
                    "alarm_flag": (state[changed] != "Норма").astype(int).values,
                }
            )
        )
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["channel_id", "ts", "raw_value", "alarm_flag"])


def load_events():
    frame = pd.read_csv(DATA, usecols=["timestamp", *BINARY_SIGNALS, *ANALOG_SIGNALS], parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    parts = []
    for signal in BINARY_SIGNALS:
        values = frame[signal].astype(int)
        changed = values.ne(values.shift(1))
        changed.iloc[0] = True
        events = pd.DataFrame(
            {
                "channel_id": signal,
                "ts": frame.loc[changed, "timestamp"].values,
                "raw_value": np.where(values[changed].values == 1, "Активен", "Норма"),
                "alarm_flag": 1 if signal in ALARM_SIGNALS else 0,
            }
        )
        parts.append(events)
    parts.append(analog_events(frame, TRAIN_END))
    combined = pd.concat(parts, ignore_index=True)
    return combined.sort_values(["channel_id", "ts"]).reset_index(drop=True)


def failure_episodes(channels):
    rows = []
    for channel in channels:
        for start, end in FAILURES:
            rows.append({"channel_id": channel, "episode_start": pd.Timestamp(start), "episode_end": pd.Timestamp(end)})
    return pd.DataFrame(rows)


def build_candidates(events):
    parts = []
    for channel_id, group in events.groupby("channel_id", observed=True):
        group = group.reset_index(drop=True)
        parts.append(group[["channel_id", "ts"]])
        span = pd.date_range(group["ts"].min().ceil("h"), group["ts"].max().floor("h"), freq="6h")
        parts.append(pd.DataFrame({"channel_id": channel_id, "ts": span}))
    candidates = pd.concat(parts, ignore_index=True)
    return candidates.drop_duplicates(subset=["channel_id", "ts"]).sort_values(["channel_id", "ts"]).reset_index(drop=True)


def main() -> None:
    events = load_events()
    channels = sorted(events["channel_id"].unique())
    episodes = failure_episodes(channels)

    candidates = build_candidates(events)
    features = features_mod.compute_features(candidates, events, episodes, numeric_mode=False, duty_cycle_mode=False)
    frame = episodes_mod.assign_targets(features, episodes, HORIZON_HOURS)
    columns = [column for column in training.feature_columns() if column in frame.columns]

    train_mask = (frame["ts"] < TRAIN_END).values
    valid_mask = ~train_mask
    if frame.loc[train_mask, "target"].sum() == 0 or frame.loc[valid_mask, "target"].sum() == 0:
        raise SystemExit("train or validation split contains no failures")

    model = model_zoo.LightGBMModel({"n_estimators": 200, "num_leaves": 31, "min_child_samples": 200})
    model.fit(frame.loc[train_mask, columns], frame.loc[train_mask, "target"].values)
    scores = model.predict_proba(frame.loc[valid_mask, columns])
    valid = frame.loc[valid_mask, ["channel_id", "ts", "target"]].assign(score=scores)

    threshold = float(np.quantile(valid["score"], 0.99))
    per_failure = []
    for start, end in FAILURES:
        start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)
        if start_ts < TRAIN_END:
            continue
        window = valid[(valid["ts"] >= start_ts - pd.Timedelta(hours=HORIZON_HOURS)) & (valid["ts"] < start_ts)]
        alerted = window[window["score"] >= threshold]
        per_failure.append(
            {
                "failure_start": start,
                "candidates_in_window": int(len(window)),
                "max_score": round(float(window["score"].max()), 4) if len(window) else None,
                "score_percentile": round(float((valid["score"] < window["score"].max()).mean()), 4)
                if len(window)
                else None,
                "alerted_before_failure": bool(len(alerted)),
                "lead_time_hours": round(float((start_ts - alerted["ts"].min()).total_seconds() / 3600), 2)
                if len(alerted)
                else None,
            }
        )

    routine = valid[valid["target"] == 0]["score"]
    frontier = fm.frontier_metrics(valid["target"].values, valid["score"].values)
    report = {
        "pr_auc": round(float(frontier["pr_auc"]), 4),
        "roc_auc": round(float(frontier["roc_auc"]), 4),
        "base_rate": round(float(valid["target"].mean()), 4),
        "dataset": "MetroPT-3 air production unit",
        "channel_kinds": {"binary": len(BINARY_SIGNALS), "analog_bands": len(ANALOG_SIGNALS)},
        "channels": channels,
        "events": int(len(events)),
        "candidates": int(len(frame)),
        "train_until": str(TRAIN_END.date()),
        "validation_failures": len(per_failure),
        "alert_threshold_top1pct": round(threshold, 4),
        "median_routine_score": round(float(routine.median()), 4),
        "alerts_per_day": round(float((valid["score"] >= threshold).sum())
                                / max((valid["ts"].max() - valid["ts"].min()).total_seconds() / 86400.0, 1.0), 2),
        "per_failure": per_failure,
        "note": (
            "Four documented failures do not support a precision estimate. "
            "The check is whether the pipeline separates pre-failure windows from routine operation."
        ),
    }

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
