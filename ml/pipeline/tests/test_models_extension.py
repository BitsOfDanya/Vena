"""Regression checks for flooding, access analytics, calibration and retraining."""

import json

import numpy as np
import pandas as pd

from pipeline import artifacts, config
from pipeline.targets import access, flood


def _weather():
    days = pd.date_range("2025-06-01", periods=10, freq="D")
    return pd.DataFrame({
        "day": days,
        "precipitation": np.arange(10, dtype=float),
        "temp_mean": np.full(10, 5.0),
        "temp_min": np.full(10, -1.0),
    })


def test_past_weather_uses_only_days_before_the_candidate():
    row = flood.weather_features([pd.Timestamp("2025-06-05 13:00")], _weather()).iloc[0]
    assert row["precip_prev_1d"] == 3.0
    assert row["precip_prev_3d"] == 1.0 + 2.0 + 3.0
    assert row["precip_forecast_0d"] == 4.0
    assert row["precip_forecast_1d"] == 5.0


def _access_events(times, channel="d1", sensor="КД Дверь"):
    return pd.DataFrame({
        "channel_id": channel,
        "ts": pd.to_datetime(times),
        "sensor_type": sensor,
        "object": "15",
    })


def test_access_scores_only_triggers_while_armed():
    guard = pd.DataFrame({
        "object": ["15", "15"],
        "ts": pd.to_datetime(["2025-01-01 20:00", "2025-01-02 08:00"]),
        "guard_state": [access.ARMED, access.DISARMED],
    })
    events = _access_events(["2025-01-01 23:30", "2025-01-02 10:00"])
    scored = access.assess(events, guard)
    assert scored["ts"].tolist() == [pd.Timestamp("2025-01-01 23:30")]
    assert bool(scored["night"].iloc[0])


def test_access_rarity_ignores_later_triggers():
    guard = pd.DataFrame({"object": ["15"], "ts": [pd.Timestamp("2024-01-01")], "guard_state": [access.ARMED]})
    times = list(pd.date_range("2024-01-02 10:00", periods=access.MIN_HISTORY, freq="7D")) + [
        pd.Timestamp("2025-01-01 03:00")
    ]
    early = access.assess(_access_events(times), guard)
    later = access.assess(_access_events(times + [pd.Timestamp("2025-06-01 03:00")] * 20), guard)
    target = pd.Timestamp("2025-01-01 03:00")
    assert early.loc[early["ts"] == target, "rarity"].iloc[0] == later.loc[later["ts"] == target, "rarity"].iloc[0]
    assert early.loc[early["ts"] == target, "rarity"].iloc[0] == 1.0


def test_calibrator_is_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    artifacts.save_artifact("plain", object(), [], {}, {}, {}, version="v")
    assert artifacts.load_calibrator("plain") is None


def test_retraining_keeps_the_better_champion(tmp_path, monkeypatch):
    import run_production_refresh as refresh

    monkeypatch.setattr(config, "ROOT", str(tmp_path))
    (tmp_path / "configs" / "models").mkdir(parents=True)

    def freeze(ap):
        artifacts.save_artifact("m", {"ap": ap}, [], {}, {}, {"test": {"avg_precision": ap}}, version=str(ap))

    freeze(0.40)
    refresh.challenge(["m"], lambda: freeze(0.30))
    assert json.loads((tmp_path / "artifacts" / "models" / "m" / "meta.json").read_text())["version"] == "0.4"
    refresh.challenge(["m"], lambda: freeze(0.45))
    assert json.loads((tmp_path / "artifacts" / "models" / "m" / "meta.json").read_text())["version"] == "0.45"
    # A model promoted by the refit study is measured on another period, so the new
    # reference replaces it and the refit study decides again.
    artifacts.save_artifact("m", {"ap": 0.9}, [], {}, {"train_years": "2019-2025"}, {"test": {"avg_precision": 0.9}}, version="refit")
    refresh.challenge(["m"], lambda: freeze(0.41))
    assert json.loads((tmp_path / "artifacts" / "models" / "m" / "meta.json").read_text())["version"] == "0.41"


def test_contributions_add_up_to_the_model_logit():
    from pipeline import explain
    from pipeline.models import LogisticRegressionModel
    from pipeline.targets.model_zoo import LightGBMModel

    rng = np.random.default_rng(0)
    features = pd.DataFrame(rng.normal(size=(400, 3)), columns=["failures_1d", "events_24h", "hour"])
    target = (features["failures_1d"] + 0.5 * rng.normal(size=400) > 0).astype(int)
    for model in (LogisticRegressionModel(), LightGBMModel({"n_estimators": 20, "num_leaves": 4, "min_child_samples": 10, "n_jobs": 1})):
        model.fit(features, target)
        score = model.predict_proba(features)
        logit = np.log(score / (1 - score))
        summed = explain.contributions(model, features).sum(axis=1).to_numpy()
        # The remaining difference is the constant bias term.
        assert np.allclose(logit - summed, (logit - summed)[0], atol=1e-6)
    drivers = explain.drivers(model, features.iloc[[int(np.argmax(score))]])
    assert "hour" not in {item["feature"] for item in drivers}
    assert drivers[0]["label"] == "Эпизодов за 1 сут"


def test_prospective_check_matures_forecasts_after_their_horizon():
    from pipeline.prospective import ProspectiveMonitor

    start = pd.Timestamp("2026-07-01")
    monitor = ProspectiveMonitor(start)
    rows = [
        {"model_id": "phase_24h", "channel_id": "a", "scored_at": "2026-07-01T10:00:00", "horizon_hours": 24,
         "score": 0.8, "model_risk_level": "critical", "target_state": "Обесточен", "sensor_type": "Состояние фазы"},
        {"model_id": "phase_24h", "channel_id": "b", "scored_at": "2026-07-01T10:00:00", "horizon_hours": 24,
         "score": 0.1, "model_risk_level": "low", "target_state": "Обесточен", "sensor_type": "Состояние фазы"},
        {"model_id": "phase_24h", "channel_id": "a", "scored_at": "2026-06-30T10:00:00", "horizon_hours": 24,
         "score": 0.9, "model_risk_level": "critical", "target_state": "Обесточен", "sensor_type": "Состояние фазы"},
    ]
    monitor.record(rows)
    events = pd.DataFrame({
        "channel_id": ["a", "a", "b"],
        "ts": pd.to_datetime(["2026-07-01T09:00:00", "2026-07-01T20:00:00", "2026-07-01T12:00:00"]),
        "alarm_flag": [0, 1, 0],
        "raw_value": ["Норма", "Обесточен", "Норма"],
    })
    early = monitor.evaluate({"Состояние фазы": events}, pd.Timestamp("2026-07-02T05:00:00"))
    assert early["models"] == {}
    report = monitor.evaluate({"Состояние фазы": events}, pd.Timestamp("2026-07-02T12:00:00"))["models"]["phase_24h"]
    assert report["forecasts"] == 2
    assert report["event_rate"] == 0.5
    assert report["alert_precision"] == 1.0


def test_inbox_batches_are_read_in_order(tmp_path):
    import stream_scoring

    (tmp_path / "2-b.jsonl").write_text(
        json.dumps({"event_id": "2", "channel_id": "7", "ts": "2026-07-01T10:00:00", "value": "Норма", "alarm": False}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "1-a.jsonl").write_text(
        json.dumps({"event_id": "1", "channel_id": "7", "ts": "2026-07-01T09:00:00", "value": "Неисправен", "alarm": True}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / ".3-c.jsonl.tmp").write_text("partial", encoding="utf-8")
    batch, files = stream_scoring.read_inbox(str(tmp_path))
    assert files == ["1-a.jsonl", "2-b.jsonl"]
    assert batch["raw_value"].tolist() == ["Неисправен", "Норма"]
    assert batch["alarm_flag"].tolist() == [1, 0]


def test_population_stability_flags_a_shifted_score():
    import run_model_report

    rng = np.random.default_rng(1)
    reference = rng.normal(size=5000)
    assert run_model_report.psi(reference, rng.normal(size=5000)) < 0.05
    assert run_model_report.psi(reference, rng.normal(loc=1.5, size=5000)) > 0.25


def test_every_recipe_fits_and_scores(monkeypatch):
    from pipeline import recipes

    # A multi-threaded LightGBM before torch hangs the later sequence tests on macOS.
    monkeypatch.setattr(recipes, "LIGHTGBM_PARAMS", {**recipes.LIGHTGBM_PARAMS, "n_jobs": 1})
    monkeypatch.setattr(recipes, "BLEND_TREE_PARAMS", {**recipes.BLEND_TREE_PARAMS, "n_jobs": 1})
    rng = np.random.default_rng(3)
    features = pd.DataFrame(rng.normal(size=(600, 4)), columns=list("abcd"))
    target = (features["a"] + rng.normal(scale=0.5, size=600) > 0.8).astype(int)
    for recipe in recipes.RECIPES:
        score = recipes.fit(recipe, features, target).predict_proba(features)
        assert score.shape == (600,)
        assert np.all((score >= 0) & (score <= 1))
        assert np.corrcoef(score, features["a"])[0, 1] > 0.5


def test_workload_rows_only_use_counts_before_the_forecast_day():
    import run_workload_forecast as workload

    days = pd.date_range("2024-01-01", "2025-03-31", freq="D")
    series = pd.Series(np.arange(len(days), dtype=float) % 9, index=days)
    weather = _weather().set_index("day")
    origin = pd.Timestamp("2025-02-01")
    before = workload.rows(series, weather, [origin])
    changed = series.copy()
    changed[changed.index >= origin] += 100
    after = workload.rows(changed, weather, [origin])
    features = [column for column in before.columns if column != "target"]
    pd.testing.assert_frame_equal(before[features], after[features])
    assert (after["target"] - before["target"] == 100).all()
    assert before["lead"].tolist() == list(workload.LEADS)
