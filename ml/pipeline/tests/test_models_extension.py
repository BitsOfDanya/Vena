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


def test_contributions_add_up_to_the_model_logit():
    from pipeline import explain
    from pipeline.models import LogisticRegressionModel
    from pipeline.targets.model_zoo import LightGBMModel

    rng = np.random.default_rng(0)
    features = pd.DataFrame(rng.normal(size=(400, 3)), columns=["failures_1d", "events_24h", "hour"])
    target = (features["failures_1d"] + 0.5 * rng.normal(size=400) > 0).astype(int)
    for model in (LogisticRegressionModel(), LightGBMModel({"n_estimators": 20, "num_leaves": 4, "min_child_samples": 10})):
        model.fit(features, target)
        score = model.predict_proba(features)
        logit = np.log(score / (1 - score))
        summed = explain.contributions(model, features).sum(axis=1).to_numpy()
        # The remaining difference is the constant bias term.
        assert np.allclose(logit - summed, (logit - summed)[0], atol=1e-6)
    drivers = explain.drivers(model, features.iloc[[int(np.argmax(score))]])
    assert "hour" not in {item["feature"] for item in drivers}
    assert drivers[0]["label"] == "Эпизодов за 1 сут"
