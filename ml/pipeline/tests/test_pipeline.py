import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from pipeline import alerts as alerts_mod
from pipeline import backtest as backtest_mod
from pipeline import candidates as candidates_mod
from pipeline import config, splits
from pipeline import episodes as episodes_mod
from pipeline import features as features_mod


def _synthetic_channel(n=400, seed=0):
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2022-01-01")
    gaps_minutes = rng.exponential(scale=30, size=n)
    ts = start + pd.to_timedelta(np.cumsum(gaps_minutes), unit="m")
    values = np.where(rng.random(n) < 0.02, config.FAULT_LITERAL, "Норма")
    df = pd.DataFrame({
        "channel_id": "C1",
        "ts": ts,
        "alarm_flag": (rng.random(n) < 0.05).astype("int8"),
        "raw_value": values,
        "tag": "100.1.2.3.",
        "system_type": "Тест",
    })
    return df


def test_burst_threshold_is_causal():
    df = _synthetic_channel(n=500, seed=1)
    g = df.reset_index(drop=True)
    mask = candidates_mod._burst_mask(g)
    gap = g["ts"].diff().dt.total_seconds()
    for i in range(config.BURST_MIN_HISTORY_EVENTS, len(g)):
        history = gap.iloc[:i]
        threshold = history.quantile(config.BURST_INTERARRIVAL_PERCENTILE / 100)
        expected = bool(gap.iloc[i] < threshold) if pd.notna(threshold) else False
        assert bool(mask.iloc[i]) == expected, f"burst mask uses future data at row {i}"


def test_burst_threshold_ignores_future_spike():
    base = _synthetic_channel(n=100, seed=2)
    tail_no_spike = base.copy()
    tail_with_spike = base.copy()
    extra_ts = tail_with_spike["ts"].iloc[-1] + pd.Timedelta(seconds=1)
    spike_row = tail_with_spike.iloc[[-1]].copy()
    spike_row["ts"] = extra_ts
    tail_with_spike = pd.concat([tail_with_spike, spike_row], ignore_index=True)

    mask_a = candidates_mod._burst_mask(tail_no_spike.reset_index(drop=True))
    mask_b = candidates_mod._burst_mask(tail_with_spike.reset_index(drop=True))
    assert (mask_a.values == mask_b.values[:len(mask_a)]).all()


def test_candidates_exclude_fault_state_itself():
    df = _synthetic_channel(n=300, seed=3)
    cand = candidates_mod.generate_candidates(df, "Состояние насоса")
    fault_ts = set(df.loc[df["raw_value"] == config.FAULT_LITERAL, "ts"])
    triggered_ts = set(cand.loc[cand["trigger"] != "silence", "ts"])
    assert not (fault_ts & triggered_ts)


def test_episode_targets_only_look_forward():
    df = _synthetic_channel(n=600, seed=4)
    episodes = episodes_mod.build_episodes(df)
    if episodes.empty:
        pytest.skip("no synthetic failures generated for this seed")
    cand = pd.DataFrame({
        "channel_id": episodes["channel_id"],
        "ts": episodes["episode_start"] - pd.Timedelta(hours=1),
    })
    labeled = episodes_mod.assign_targets(cand, episodes, horizon_hours=24)
    assert (labeled["target"] == 1).all()

    cand_after = pd.DataFrame({
        "channel_id": episodes["channel_id"],
        "ts": episodes["episode_end"] + pd.Timedelta(hours=1000),
    })
    labeled_after = episodes_mod.assign_targets(cand_after, episodes, horizon_hours=24)
    assert (labeled_after["target"] == 0).all()


def test_features_only_use_past_events():
    df = _synthetic_channel(n=500, seed=5).reset_index(drop=True)
    episodes = episodes_mod.build_episodes(df)
    mid = len(df) // 2
    cand_ts = df["ts"].iloc[[mid]].values
    ev_ts = df["ts"].values
    ev_alarm = df["alarm_flag"].values
    ev_value = df["raw_value"].values
    fail_starts = episodes.loc[episodes["channel_id"] == "C1", "episode_start"].values if len(episodes) else np.array([], dtype="datetime64[s]")

    full = features_mod._channel_features(cand_ts, ev_ts, ev_alarm, ev_value, fail_starts)
    truncated = features_mod._channel_features(cand_ts, ev_ts[:mid + 1], ev_alarm[:mid + 1], ev_value[:mid + 1], fail_starts)

    for key in full:
        assert np.allclose(full[key], truncated[key], equal_nan=True), f"feature {key} depends on future events"


def test_split_periods_do_not_overlap():
    ts = pd.date_range("2019-01-01", "2026-06-30", freq="17D")
    df = pd.DataFrame({"ts": ts})
    out = splits.assign_split(df)
    train_years = out.loc[out["split"] == "train", "ts"].dt.year
    valid_years = out.loc[out["split"] == "valid", "ts"].dt.year
    test_years = out.loc[out["split"] == "test", "ts"].dt.year
    assert train_years.max() <= config.TRAIN_YEARS[1]
    assert (valid_years == config.VALID_YEAR).all()
    assert test_years.min() >= config.TEST_YEARS[0]
    assert train_years.max() < valid_years.min() if len(valid_years) else True
    assert valid_years.max() < test_years.min() if len(test_years) and len(valid_years) else True


def test_feature_columns_shared_between_run_and_experiments():
    from pipeline import training
    assert training.feature_columns() == list(features_mod.FEATURE_COLUMNS)
    from pipeline import experiments as experiments_mod
    from pipeline import run as run_mod
    assert run_mod.training.feature_columns is training.feature_columns
    assert experiments_mod.training.feature_columns is training.feature_columns


def test_model_output_example_matches_schema():
    fixture_dir = os.path.join(os.path.dirname(__file__), "fixtures")
    with open(os.path.join(fixture_dir, "model_output_schema.json")) as f:
        schema = json.load(f)
    with open(os.path.join(fixture_dir, "model_output_example.json")) as f:
        example = json.load(f)

    for key in schema["required"]:
        assert key in example, f"missing required field {key}"
    for key, spec in schema["properties"].items():
        if key not in example:
            continue
        py_type = {"string": str, "number": (int, float), "integer": int, "object": dict, "array": list}[spec["type"]]
        assert isinstance(example[key], py_type), f"field {key} has wrong type"


def test_resolve_sensor_type_rejects_unknown():
    from pipeline import run as run_mod
    with pytest.raises(ValueError):
        run_mod.resolve_sensor_type("not_a_real_sensor")
    assert run_mod.resolve_sensor_type("pump") == "Состояние насоса"


def test_candidate_coverage_detects_and_misses():
    episodes = pd.DataFrame({
        "channel_id": ["A", "A", "B"],
        "episode_start": pd.to_datetime(["2022-01-05 10:00", "2022-01-10 10:00", "2022-01-05 10:00"]),
    })
    candidates = pd.DataFrame({
        "channel_id": ["A", "A", "B"],
        "ts": pd.to_datetime(["2022-01-05 08:00", "2022-01-09 12:00", "2022-01-01 00:00"]),
    })
    covered = alerts_mod.candidate_coverage(candidates, episodes, horizon_hours=24)
    assert covered.tolist() == [True, True, False]


def test_apply_cooldown_suppresses_within_window_same_channel():
    points = pd.DataFrame({
        "channel_id": ["A", "A", "A", "B"],
        "ts": pd.to_datetime(["2022-01-01 00:00", "2022-01-01 10:00", "2022-01-02 06:00", "2022-01-01 05:00"]),
    })
    kept = alerts_mod._apply_cooldown(points, cooldown_hours=24)
    kept_ts = sorted(kept["ts"].dt.strftime("%Y-%m-%d %H:%M").tolist())
    assert kept_ts == ["2022-01-01 00:00", "2022-01-01 05:00", "2022-01-02 06:00"]


def test_episode_level_recall_dedups_and_reports_earliest_lead_time():
    episodes = pd.DataFrame({
        "channel_id": ["A"],
        "episode_start": pd.to_datetime(["2022-01-05 10:00"]),
    })
    alerts = pd.DataFrame({
        "channel_id": ["A", "A"],
        "ts": pd.to_datetime(["2022-01-04 10:00", "2022-01-05 08:00"]),
    })
    detected, lead = alerts_mod.episode_level_recall(alerts, episodes, horizon_hours=48)
    assert detected.tolist() == [True]
    assert lead[0] == pytest.approx(24.0)


def test_backtest_fold_uses_only_train_period():
    ts = pd.date_range("2019-01-01", "2025-12-31", freq="30D")
    df = pd.DataFrame({"ts": ts, "channel_id": "A", "target": 0})
    fold = {"name": "fold1", "train_end": 2021, "valid_year": 2022}
    out = backtest_mod.assign_fold(df, fold)
    train_years = out.loc[out["fold_split"] == "train", "ts"].dt.year
    valid_years = out.loc[out["fold_split"] == "valid", "ts"].dt.year
    assert train_years.max() <= 2021
    assert (valid_years == 2022).all()
    assert train_years.max() < valid_years.min()


def test_global_rates_computed_from_train_only():
    events = pd.DataFrame({
        "ts": pd.to_datetime(["2020-06-01", "2025-06-01", "2025-06-02"]),
        "channel_id": ["A", "A", "A"],
        "alarm_flag": [0, 1, 1],
        "raw_value": ["Норма", config.FAULT_LITERAL, "Норма"],
    })
    rates = features_mod.compute_global_rates(events, train_end_year=2021)
    assert rates["failure"] == 0.0
    assert rates["alarm"] == 0.0


def test_calibration_fit_uses_only_validation_data():
    from pipeline import calibration
    rng = np.random.default_rng(3)
    valid_scores = rng.random(200)
    valid_targets = (valid_scores + rng.normal(scale=0.1, size=200) > 0.5).astype(int)
    different_test_scores = rng.random(50)
    different_test_targets = rng.integers(0, 2, 50)
    class DummyModel:
        def predict_proba(self, X):
            return X["score"].values
    valid_df = pd.DataFrame({"score": valid_scores, "target": valid_targets})
    test_df_a = pd.DataFrame({"score": different_test_scores, "target": different_test_targets})
    test_df_b = pd.DataFrame({"score": different_test_scores, "target": 1 - different_test_targets})
    res_a = calibration.calibrate_and_evaluate(DummyModel(), valid_df, test_df_a, ["score"], method="isotonic")
    res_b = calibration.calibrate_and_evaluate(DummyModel(), valid_df, test_df_b, ["score"], method="isotonic")
    np.testing.assert_array_equal(res_a["calibrator"].f_(np.array([0.1, 0.5, 0.9])),
                                   res_b["calibrator"].f_(np.array([0.1, 0.5, 0.9])))


def test_ranking_group_boundaries_are_contiguous_and_complete():
    ts = pd.to_datetime(["2022-01-01 01:00", "2022-01-02 03:00", "2022-01-01 05:00",
                          "2022-01-03 00:00", "2022-01-02 20:00"])
    group_id = ts.floor("D").astype("int64").values
    order = np.argsort(group_id, kind="stable")
    sizes = pd.Series(group_id[order]).value_counts().sort_index().values
    assert sizes.sum() == len(ts)
    assert len(sizes) == ts.floor("D").nunique()
    sorted_groups = group_id[order]
    assert (np.diff(sorted_groups) >= 0).all()


def test_freeze_threshold_is_reused_unchanged_on_new_data():
    from pipeline import decision
    rng = np.random.default_rng(5)
    valid_scores = rng.random(500)
    valid_targets = (valid_scores > 0.6).astype(int)
    frozen = decision.freeze_threshold_max_recall_at_precision(valid_targets, valid_scores, min_precision=0.7)
    assert frozen is not None
    test_scores = rng.random(300)
    test_targets = (test_scores > 0.6).astype(int)
    applied = decision.apply_frozen_threshold(test_targets, test_scores, frozen["threshold"])
    assert applied["threshold"] == frozen["threshold"]


def test_inference_feature_parity_with_batch_pipeline():
    from pipeline import inference
    df = _synthetic_channel(n=300, seed=9).reset_index(drop=True)
    episodes = episodes_mod.build_episodes(df)
    candidates_df = pd.DataFrame({"channel_id": ["C1"], "ts": [df["ts"].iloc[150]]})
    global_rates = features_mod.compute_global_rates(df, train_end_year=2022)
    batch = features_mod.compute_features(candidates_df, df, episodes, global_rates=global_rates)

    channel_events = df[df["channel_id"] == "C1"]
    channel_episodes = episodes[episodes["channel_id"] == "C1"]
    row = inference.build_feature_row(
        df["ts"].iloc[150], channel_events, channel_episodes,
        {"numeric_mode": False, "duty_cycle_mode": False, "global_rates": global_rates},
    )
    for col in features_mod.FEATURE_COLUMNS:
        assert np.isclose(batch[col].iloc[0], row[col].iloc[0], equal_nan=True), f"parity mismatch on {col}"


def test_artifact_save_and_load_roundtrip(tmp_path, monkeypatch):
    from pipeline import artifacts
    from pipeline import models as models_mod
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    monkeypatch.setattr(artifacts.config, "ROOT", str(tmp_path))
    model = models_mod.LogisticRegressionModel()
    X = pd.DataFrame({"f1": [0.1, 0.2, 0.9, 0.8], "f2": [1, 0, 1, 0]})
    y = pd.Series([0, 0, 1, 1])
    model.fit(X, y)
    artifacts.save_artifact(
        "test_device", model, ["f1", "f2"], {"model_name": "logistic_regression", "horizon_hours": 24},
        {"train_years": "2019-2023"}, {"avg_precision": 0.5}, "v1",
    )
    loaded_model, meta = artifacts.load_artifact("test_device")
    assert meta["feature_columns"] == ["f1", "f2"]
    assert meta["version"] == "v1"
    np.testing.assert_allclose(loaded_model.predict_proba(X), model.predict_proba(X))


def test_candidate_ablation_trigger_removes_alarm_points():
    df = _synthetic_channel(n=200, seed=7)
    df["alarm_flag"] = 0
    df.loc[df.index[5], "alarm_flag"] = 1
    full = candidates_mod.generate_candidates(df, "Состояние насоса")
    without_alarm = candidates_mod.generate_candidates(df, "Состояние насоса", exclude_triggers=["alarm"])
    assert (full["trigger"] == "alarm").any()
    assert not (without_alarm["trigger"] == "alarm").any()


@pytest.mark.slow
def test_cli_smoke_and_determinism():
    cmd = [sys.executable, "-m", "pipeline.run", "--sensor-type", "temperature",
           "--horizon", "24", "--models", "logistic_regression"]
    r1 = subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True, timeout=300, check=False)
    assert r1.returncode == 0, r1.stderr
    r2 = subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True, timeout=300, check=False)
    assert r2.returncode == 0, r2.stderr
    assert r1.stdout.strip().splitlines()[-2:] == r2.stdout.strip().splitlines()[-2:]
