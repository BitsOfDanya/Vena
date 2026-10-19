import numpy as np
import pandas as pd

from pipeline import object_risk


def _registry():
    t0 = pd.to_datetime(["2026-01-01 10:00", "2026-01-09 08:00", "2026-01-10 03:00"])
    return {
        "power": pd.DataFrame({"object": ["A", "A", "B"], "t0": t0}),
        "flood": pd.DataFrame({"object": [], "t0": pd.to_datetime([])}),
        "fire": None,
    }


def test_features_use_only_previous_days():
    out = object_risk.features(_registry(), ["A", "B", "C"], "2026-01-10 15:00").set_index("object")
    assert out.loc["A", "power_1d"] == 1 and out.loc["A", "power_30d"] == 2
    assert out.loc["B", "power_1d"] == 0 and out.loc["B", "power_days_since"] == 9999
    assert out.loc["A", "power_days_since"] == 1
    assert out.loc["C", "flood_90d"] == 0 and out.loc["C", "fire_days_since"] == 9999
    assert out.loc["A", "month"] == 1 and out.loc["A", "weekday"] == 5


def test_ecdf_against_reference():
    reference = np.linspace(0, 1, 11)
    assert object_risk.ecdf([-1.0, 0.5, 2.0], reference).tolist() == [0.0, 6 / 11, 1.0]


def test_channel_by_object_takes_max_raw_score():
    predictions = [
        {"channel_id": "1", "model_id": "phase_24h", "raw_score": 0.2},
        {"channel_id": "2", "model_id": "phase_24h", "raw_score": 0.7},
        {"channel_id": "3", "model_id": "phase_24h", "raw_score": 0.4},
        {"channel_id": "9", "model_id": "phase_24h", "raw_score": 0.9},
    ]
    out = object_risk.channel_by_object(predictions, {"1": "A", "2": "A", "3": "B"})
    assert out == {("phase_24h", "A"): 0.7, ("phase_24h", "B"): 0.4}


def test_registry_from_stream_events():
    ts = pd.to_datetime(["2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:02"])
    events = {"Состояние фазы": pd.DataFrame({"channel_id": ["1", "2", "3"], "ts": ts, "raw_value": ["Обесточен"] * 3})}
    out = object_risk.registry_from(events, {"1": "A", "2": "A", "3": "A"})
    assert list(out["power"]["object"]) == ["A"]
    assert out["flood"].empty and out["fire"].empty


def test_state_panel_counts_previous_days_only():
    ts = pd.to_datetime(["2026-01-08 10:00", "2026-01-09 11:00", "2026-01-09 12:00", "2026-01-10 01:00"])
    events = {"Состояние фазы": pd.DataFrame({"channel_id": ["1", "1", "2", "1"], "ts": ts, "raw_value": ["Обесточен"] * 4})}
    out = object_risk.state_panel(events, {"1": "A", "2": "A"}, ["A", "B"], pd.date_range("2026-01-09", "2026-01-10"))
    a = out.loc[out["object"] == "A"].set_index("day")
    assert a.loc["2026-01-09", "phase_Обесточен_1d"] == 1
    assert a.loc["2026-01-10", "phase_Обесточен_1d"] == 2 and a.loc["2026-01-10", "phase_Обесточен_7d"] == 3
    assert a.loc["2026-01-10", "phase_channels_1d"] == 2
    assert out.loc[out["object"] == "B", "phase_Обесточен_30d"].sum() == 0


def test_nowcast_features_count_confirmed_incidents_only():
    flood = pd.DataFrame({"object": ["A", "A", "B"], "t0": pd.to_datetime(["2026-03-01 08:00", "2026-03-02 09:30", "2026-02-01 00:00"])})
    out = object_risk.nowcast_features(flood, ["A", "B", "C"], "2026-03-02 10:00", 60).set_index("object")
    assert out.loc["A", "incidents_24h"] == 0 and out.loc["A", "incidents_168h"] == 1
    assert out.loc["A", "hours_since_incident"] == 25.0
    assert out.loc["B", "incidents_720h"] == 1 and out.loc["C", "hours_since_incident"] == 1e5
    assert out.loc["A", "hour"] == 10


def test_health_index_combines_object_models(tmp_path, monkeypatch):
    import json

    folder = tmp_path / "object_health"
    folder.mkdir()
    (folder / "points.json").write_text(json.dumps({"raw_risk": [0.0, 1.0], "risk": [0.0, 1.0]}))
    (folder / "meta.json").write_text(json.dumps({"model_config": {"label": "Индекс", "target": "инцидент"},
                                                  "metrics_snapshot": {"test_2026h1": {"ece": 0.01, "avg_precision": 0.8}}}))
    monkeypatch.setattr(object_risk.artifacts, "artifact_dir", lambda name: str(tmp_path / name))
    rows = []
    for scenario, name, _ in object_risk.KINDS.values():
        rows.append({"object_id": "A", "model_id": name, "probability": 0.5 if scenario == "power_loss" else 0.0, "day": "2026-06-30"})
        rows.append({"object_id": "B", "model_id": name, "probability": 0.0, "day": "2026-06-30"})
    out = object_risk.health(rows)
    assert out["items"]["A"]["index"] == 50 and out["items"]["B"]["index"] == 100
    assert out["items"]["A"]["by_scenario"]["power_loss"] == 0.5
    assert object_risk.health(rows[:2]) is None
