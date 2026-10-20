import json

import numpy as np
import pandas as pd
import pytest
from pipeline import features
from pipeline.targets.discovery import state_episodes
from run_independent_validation import run_real

from validation.evaluation import (
    EPISODE_COLUMNS,
    alert_metrics,
    causal_features,
    load,
    score_channel,
    summarize,
)
from validation.simulation import simulate


def event_frame():
    return pd.DataFrame(
        {
            "channel_id": ["x"] * 6,
            "ts": pd.to_datetime(
                [
                    "2026-07-01",
                    "2026-07-02",
                    "2026-07-03",
                    "2026-07-13",
                    "2026-07-14",
                    "2026-07-20",
                ]
            ),
            "raw_value": [
                "Включен",
                "Неисправен",
                "Выключен",
                "Включен",
                "Неисправен",
                "Выключен",
            ],
            "alarm_flag": [0, 1, 0, 0, 1, 0],
        }
    )


@pytest.mark.parametrize("name", ["pump_72h", "flood_24h"])
def test_vectorized_replay_matches_each_truncated_production_feature_row(name):
    events = event_frame()
    cfg = load(name)[1]["model_config"]
    episodes = state_episodes(events, "Неисправен")
    times = pd.to_datetime(
        ["2026-07-01", "2026-07-02 08:00", "2026-07-09", "2026-07-13", "2026-07-15"],
        format="mixed",
    )
    batch = causal_features(times, events, episodes, cfg)
    for i, t in enumerate(times):
        history = events.loc[events.ts <= t]
        observed = episodes.loc[episodes.episode_start <= t]
        prefix = features.compute_features_single(
            np.array([t], dtype="datetime64[ns]"),
            history.ts.to_numpy(),
            history.alarm_flag.to_numpy(),
            history.raw_value.to_numpy(),
            observed.episode_start.to_numpy(),
            duty_cycle_mode=cfg.get("duty_cycle_mode", False),
            global_rates=cfg["global_rates"],
        )
        columns = [c for c in batch if c != "ts"]
        np.testing.assert_allclose(
            batch.loc[i, columns].astype(float),
            prefix.loc[0, columns].astype(float),
            atol=1e-12,
            err_msg=str(t),
        )


def test_future_truth_changes_labels_but_never_predictions_and_tail_is_excluded():
    events = event_frame()
    empty = pd.DataFrame(columns=EPISODE_COLUMNS)
    future = pd.DataFrame(
        [["x", pd.Timestamp("2026-07-12"), pd.Timestamp("2026-07-12 01:00")]],
        columns=EPISODE_COLUMNS,
    )
    before = score_channel(events, empty, "pump_72h", "2026-07-05", "2026-07-20")
    after = score_channel(events, future, "pump_72h", "2026-07-05", "2026-07-20")
    np.testing.assert_array_equal(before.raw_score, after.raw_score)
    assert before.target.sum() == 0 < after.target.sum()
    assert after.ts.max() + pd.Timedelta(hours=72) <= pd.Timestamp("2026-07-20")
    assert set(after.variant) == {"pump_baseline_72h"}
    at_event = after.loc[after.ts == pd.Timestamp("2026-07-12")].iloc[0]
    assert not at_event.eligible and at_event.target == 0


def test_future_observed_events_cannot_change_earlier_scores():
    events = event_frame()
    truth = pd.DataFrame(columns=EPISODE_COLUMNS)
    past = score_channel(
        events.loc[events.ts <= "2026-07-09"],
        truth,
        "pump_24h",
        "2026-07-04",
        "2026-07-10",
    )
    full = score_channel(events, truth, "pump_24h", "2026-07-04", "2026-07-10")
    np.testing.assert_allclose(past.raw_score, full.raw_score, atol=1e-12)


def test_episode_metrics_deduplicate_and_do_not_call_no_alerts_perfect_precision():
    times = pd.date_range("2026-07-01", periods=16, freq="6h")
    rows = pd.DataFrame(
        {
            "channel_id": "x",
            "ts": times,
            "horizon_hours": 24,
            "eligible": True,
            "alert": True,
            "target": 0,
        }
    )
    truth = pd.DataFrame(
        [["x", pd.Timestamp("2026-07-03"), pd.Timestamp("2026-07-03 01:00")]],
        columns=EPISODE_COLUMNS,
    )
    rows.loc[(rows.ts >= "2026-07-02") & (rows.ts < "2026-07-03"), "target"] = 1
    metric = alert_metrics(rows, truth)
    assert metric["alerts"] == 4
    assert metric["covered_episodes"] == 1
    assert metric["precision"] == 0.25
    rows["alert"] = False
    metric = alert_metrics(rows, truth)
    assert metric["precision"] is None and metric["episode_recall"] == 0


def test_physics_conserves_water_and_maintenance_is_not_a_physical_failure():
    sample = simulate("maintenance", 101)
    assert sample["parameters"]["max_mass_balance_error_m3"] < 1e-10
    assert sample["truth"].empty
    assert "Неисправен" in sample["events"].raw_value.values
    assert sample["physics"].level_m.between(0, 2.2 + 1e-12).all()


def test_power_outage_is_not_mechanical_failure():
    sample = simulate("power_loss", 101)
    assert (sample["truth"].kind == "phase").any()
    assert (sample["truth"].kind == "flood").any()
    assert not (sample["truth"].kind == "pump").any()


def test_missing_real_data_is_blocked_not_a_successful_test(tmp_path):
    report = run_real(None, tmp_path)
    assert report["status"] == "blocked_missing_data" and report["metrics"] is None


def test_real_manifest_checks_attestation_and_runs_on_normalized_csv(tmp_path):
    event_frame().to_csv(tmp_path / "events.csv", index=False)
    pd.DataFrame(
        [["x", "2026-07-12 00:00:00", "2026-07-12 01:00:00"]], columns=EPISODE_COLUMNS
    ).to_csv(tmp_path / "episodes.csv", index=False)
    manifest = {
        "events": "events.csv",
        "episodes": "episodes.csv",
        "model": "pump_24h",
        "evaluation_start": "2026-07-05",
        "coverage_end": "2026-07-20",
        "timezone": "Europe/Moscow",
        "attested_unseen": False,
        "truth_source": "Synthetic unit-test fixture, not an actual holdout",
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="attestation"):
        run_real(path, tmp_path)
    manifest["attested_unseen"] = True
    path.write_text(json.dumps(manifest))
    result = run_real(path, tmp_path)
    assert result["status"] == "completed"
    assert result["metrics"]["pump_24h"]["operations"]["episodes"] == 1
    assert (tmp_path / "real_predictions.csv.gz").exists()


def test_no_failure_population_has_no_ap_or_recall():
    events = event_frame()
    truth = pd.DataFrame(columns=EPISODE_COLUMNS)
    rows = score_channel(events, truth, "pump_24h", "2026-07-05", "2026-07-20")
    report = summarize(rows, truth)
    assert report["ap"] is None and report["operations"]["episode_recall"] is None
