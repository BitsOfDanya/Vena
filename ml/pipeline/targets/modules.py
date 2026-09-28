import json
import os

import joblib
import numpy as np
import pandas as pd

from pipeline import config, episodes as episodes_mod, extract, features as features_mod, training
from pipeline.formal import metrics as fm
from pipeline.targets import alarm, discovery, discovery_run, evaluation, model_zoo, state_target

PHASE_SENSOR = "Состояние фазы"
PHASE_STATE = "Обесточен"
MAX_VALID_YEAR = 2025


def build_phase_frame(events, horizons=(24,), sustained_minutes=30):
    frame, episodes = state_target.build_frame(events, PHASE_STATE, horizons=horizons)
    frame = frame.rename(columns={f"y{h}": f"any_y{h}" for h in horizons})
    sustained = discovery.sustained_onsets(events, PHASE_STATE, sustained_minutes)
    for h in horizons:
        frame[f"sustained_y{h}"] = episodes_mod.assign_targets(frame[["channel_id", "ts"]], sustained, h)["target"].values
    return frame, episodes, sustained


def build_alarm_frame(con=None, windows=alarm.WINDOWS_MINUTES, include_lockbox=False):
    if con is None:
        con = extract._connect()
        extract._build_views(con)
    tag_map = con.execute("SELECT ид_канала_данных, тег_инженерной_системы FROM channels").df().set_index(
        "ид_канала_данных").iloc[:, 0].to_dict()
    parts = []
    for sensor_type, states in alarm.DETECTION_STATES.items():
        ev = discovery_run.load_literal_events(con, sensor_type).sort_values(["channel_id", "ts"]).reset_index(drop=True)
        ev["channel_id"] = ev["channel_id"].astype(str)
        alarms = alarm.detection_alarms(ev, sensor_type, tag_map)
        alarms["channel_id"] = alarms["channel_id"].astype(str)
        episodes = pd.concat([discovery.state_episodes(ev, s) for s in states], ignore_index=True)
        episodes["channel_id"] = episodes["channel_id"].astype(str)
        merged = ev.assign(raw_value=ev["raw_value"].where(~ev["raw_value"].isin(states), states[0]))
        rates = state_target.global_rates(merged, states[0], config.TRAIN_YEARS[1])
        feats = features_mod.compute_features(alarms[["channel_id", "ts"]], ev, episodes, numeric_mode=False,
                                              duty_cycle_mode=False, global_rates=rates)
        parts.append(pd.concat([alarms, feats.drop(columns=["channel_id", "ts"])], axis=1))
    frame = pd.concat(parts, ignore_index=True).sort_values(["ts", "channel_id"], kind="stable").reset_index(drop=True)
    frame["sensor_code"] = frame["sensor_type"].astype("category").cat.codes
    frame = pd.concat([frame, alarm.group_history_features(frame)], axis=1)
    for w in windows:
        labels = alarm.corroboration_labels(frame, w)
        for col in labels.columns:
            frame[f"c{w}_{col}"] = labels[col].astype(int).values
    if include_lockbox:
        return frame
    return frame.loc[frame["ts"] < state_target.LOCKBOX_START].reset_index(drop=True)


def alarm_feature_columns(frame):
    history = [c for c in frame.columns if c.startswith("alarm_ch_prev_") or c.startswith("alarm_grp_prev_")]
    return training.feature_columns() + ["sensor_code"] + history


def train_and_report(frame, target_col, feature_cols, train_end_year, valid_year, out_dir, name, model_params=None):
    if valid_year > MAX_VALID_YEAR:
        raise ValueError("valid_year must not reach the lockbox period")
    year = frame["ts"].dt.year
    train = (year <= train_end_year).values
    valid = (year == valid_year).values
    model = model_zoo.LightGBMModel({"n_estimators": 300, "num_leaves": 63, **(model_params or {})})
    model.fit(frame.loc[train, feature_cols], frame.loc[train, target_col].values)
    score = model.predict_proba(frame.loc[valid, feature_cols])
    y = frame.loc[valid, target_col].values
    report = fm.frontier_metrics(y, score)
    scored = pd.DataFrame({"target": y, "score": score})
    report["threshold_precision_0.70"] = evaluation.previous_fold_threshold(scored, 0.7)
    report.update(name=name, target=target_col, train_end_year=train_end_year, valid_year=valid_year,
                  n_train=int(train.sum()), n_valid=int(valid.sum()), base_rate=float(y.mean()))
    os.makedirs(out_dir, exist_ok=True)
    joblib.dump({"model": model, "feature_columns": list(feature_cols)}, os.path.join(out_dir, f"{name}.joblib"))
    with open(os.path.join(out_dir, f"{name}_report.json"), "w") as fh:
        json.dump(report, fh, indent=1, default=float)
    return report
