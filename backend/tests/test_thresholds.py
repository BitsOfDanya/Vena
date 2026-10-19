import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.models import SettingsRecord
from app.db.session import SessionLocal
from app.domain import thresholds
from app.domain.forecast_context import (
    build_context,
    calendar_line,
    forecast_days,
    seasonality_line,
    weather_line,
)
from app.domain.predictions import reset_prediction_source
from app.schemas.predictions import Prediction

from .test_predictions import row, write_snapshot

DEFAULTS = {"critical": 0.99, "high": 0.9, "medium": 0.8}
RAW = {"100": 0.995, "200": 0.93, "300": 0.85, "400": 0.5}


@pytest.fixture()
def ml_root(tmp_path: Path):
    settings = get_settings()
    original = settings.ml_dir
    settings.ml_dir = tmp_path
    reset_prediction_source()
    yield tmp_path
    settings.ml_dir = original
    reset_prediction_source()


def scored(channel: str, raw: float) -> dict:
    level = thresholds.model_level(raw, DEFAULTS)
    item = row(channel, round(raw * 0.4, 4), level)
    item.update(raw_score=raw, thresholds=DEFAULTS, score_type="calibrated_probability")
    return item


def write_scored(root: Path, snapshot_id: str = "snap-1") -> None:
    rows = [scored(channel, raw) for channel, raw in RAW.items()]
    write_snapshot(root, datetime.now(tz=UTC), rows, snapshot_id=snapshot_id)


def levels(client: TestClient) -> dict[str, str]:
    items = client.get("/api/v1/predictions", params={"limit": 50}).json()
    return {item["asset_id"]: item["risk_level"] for item in items}


def write_curves(root: Path) -> None:
    point = {"probability": 0.3, "precision": 0.5, "recall": 0.4, "channels_per_day": 2.0}
    current = {level: {"threshold": value, **point} for level, value in DEFAULTS.items()}
    payload = {
        "period": "2026H1",
        "unit": "raw_score",
        "generated_at": "2026-10-01T00:00:00+00:00",
        "models": {
            "pump_72h": {
                "label": "Отказ насоса",
                "horizon_hours": 72,
                "base_rate": 0.12,
                "candidates": 1000,
                "days": 181,
                "current": current,
                "curve": [
                    {"threshold": 0.9, **point},
                    {"threshold": 0.2, "probability": None, "precision": None, "recall": 0.9},
                    {"threshold": 0.99, **point},
                ],
            }
        },
    }
    (root / "results" / "threshold_curves.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("override", "expected", "notifications"),
    [
        (None, {"100": "critical", "200": "attention", "300": "observe", "400": "normal"}, 2),
        (
            {"critical": 0.8, "high": 0.4, "medium": 0.2},
            {"100": "critical", "200": "critical", "300": "critical", "400": "attention"},
            4,
        ),
        (
            {"critical": 0.999, "high": 0.99, "medium": 0.9},
            {"100": "attention", "200": "observe", "300": "normal", "400": "normal"},
            1,
        ),
    ],
)
def test_override_changes_levels_and_refresh_incidents(
    client: TestClient, ml_root: Path, override, expected, notifications
) -> None:
    write_scored(ml_root)
    assert set(levels(client).values()) == {"critical", "attention", "observe", "normal"}

    if override:
        response = client.put("/api/v1/ml/thresholds/pump_72h", json=override)
        assert response.status_code == 200

    assert levels(client) == expected
    summary = client.get("/api/v1/predictions/summary").json()["counts"]
    assert summary["critical"] == list(expected.values()).count("critical")
    refresh = client.post("/api/v1/predictions/refresh").json()
    assert refresh["notifications_created"] == notifications
    assert refresh["actions_created"] == notifications


def test_catalogue_update_and_reset(client: TestClient, ml_root: Path) -> None:
    write_scored(ml_root)

    [item] = client.get("/api/v1/ml/thresholds").json()
    assert item["model_id"] == "pump_72h"
    assert item["label"] == "Неисправность насоса"
    assert item["horizon_hours"] == 72
    assert item["default"] == DEFAULTS
    assert item["override"] is None
    assert item["effective"] == DEFAULTS
    assert item["curve"] == []
    assert item["current"] == {}

    override = {"critical": 0.95, "high": 0.85, "medium": 0.6}
    updated = client.put("/api/v1/ml/thresholds/pump_72h", json=override).json()
    assert updated["override"] == override
    assert updated["effective"] == override
    assert updated["default"] == DEFAULTS
    assert levels(client)["300"] == "attention"

    reset = client.delete("/api/v1/ml/thresholds/pump_72h").json()
    assert reset["override"] is None
    assert reset["effective"] == DEFAULTS
    assert levels(client)["300"] == "observe"

    actions = [entry["action"] for entry in client.get("/api/v1/audit").json()]
    assert "settings.thresholds.update" in actions
    assert "settings.thresholds.reset" in actions


def test_curves_file_is_served_sorted(client: TestClient, ml_root: Path) -> None:
    write_scored(ml_root)
    write_curves(ml_root)

    [item] = client.get("/api/v1/ml/thresholds").json()

    assert item["label"] == "Отказ насоса"
    assert item["period"] == "2026H1"
    assert item["base_rate"] == 0.12
    assert [point["threshold"] for point in item["curve"]] == [0.2, 0.9, 0.99]
    assert item["curve"][0]["precision"] is None
    assert item["current"]["high"]["threshold"] == 0.9
    assert item["current"]["high"]["channels_per_day"] == 2.0


def test_validation_rejects_bad_thresholds(client: TestClient, ml_root: Path) -> None:
    write_scored(ml_root)
    path = "/api/v1/ml/thresholds/pump_72h"

    assert client.put(path, json={"critical": 0.8, "high": 0.9, "medium": 0.5}).status_code == 422
    assert client.put(path, json={"critical": 0.9, "high": 0.5, "medium": 0.6}).status_code == 422
    assert client.put(path, json={"critical": 1.2, "high": 0.9, "medium": 0.5}).status_code == 422
    assert client.put(path, json={"critical": 0.9, "high": 0.5, "medium": 0}).status_code == 422
    assert client.put(path, json={"critical": 0.9, "high": 0.5}).status_code == 422
    unknown = {"critical": 0.9, "high": 0.5, "medium": 0.2}
    assert client.put("/api/v1/ml/thresholds/nope_24h", json=unknown).status_code == 404
    assert client.get("/api/v1/ml/thresholds").json()[0]["override"] is None
    assert client.put(path, json={"critical": 1, "high": 1, "medium": 1}).status_code == 200


def test_only_admin_changes_thresholds(client: TestClient, ml_root: Path, auth_users) -> None:
    write_scored(ml_root)
    path = "/api/v1/ml/thresholds/pump_72h"
    body = {"critical": 0.95, "high": 0.85, "medium": 0.6}

    assert client.get("/api/v1/ml/thresholds").status_code == 401
    assert client.get("/api/v1/ml/thresholds", headers=auth_users["viewer"]).status_code == 200
    assert client.put(path, json=body, headers=auth_users["viewer"]).status_code == 403
    assert client.put(path, json=body, headers=auth_users["dispatcher"]).status_code == 403
    assert client.delete(path, headers=auth_users["dispatcher"]).status_code == 403
    assert client.put(path, json=body, headers=auth_users["admin"]).status_code == 200
    assert client.delete(path, headers=auth_users["admin"]).status_code == 200


def test_change_from_another_worker_applies_without_restart(
    client: TestClient, ml_root: Path, monkeypatch
) -> None:
    write_scored(ml_root)
    assert levels(client)["400"] == "normal"

    monkeypatch.setattr(thresholds, "REFRESH_SECONDS", 0.0)
    with SessionLocal.begin() as session:
        value = json.dumps({"pump_72h": {"critical": 0.6, "high": 0.55, "medium": 0.4}})
        session.add(SettingsRecord(key=thresholds.SETTINGS_KEY, value=value))

    assert levels(client) == {
        "100": "critical",
        "200": "critical",
        "300": "critical",
        "400": "observe",
    }


def prediction(time: datetime, horizon: int = 24, device: str = "phase") -> Prediction:
    return Prediction(
        id="snap:model:1",
        asset_id="1",
        device_type=device,
        model_id=f"{device}_{horizon}h",
        model_version=None,
        prediction_time=time,
        horizon_hours=horizon,
        score=0.4,
        score_type="calibrated_probability",
        risk_level="attention",
        model_risk_level="high",
        predicted_event_type="power_loss",
        source_snapshot="snap",
    )


def test_forecast_window_days_follow_horizon() -> None:
    evening = datetime(2026, 6, 30, 20, 59, tzinfo=UTC)

    assert forecast_days(prediction(evening), "Europe/Moscow") == [date(2026, 7, 1)]
    assert forecast_days(prediction(evening, 72), "Europe/Moscow") == [
        date(2026, 7, 1),
        date(2026, 7, 2),
        date(2026, 7, 3),
    ]


def test_calendar_line_marks_weekends_and_holidays() -> None:
    assert calendar_line([date(2026, 7, 1)]).text == "Среда, 1 июля — рабочий день"
    assert calendar_line([date(2026, 7, 4)]).text == "Суббота, 4 июля — выходной день"
    assert (
        calendar_line([date(2026, 11, 4)]).text
        == "Среда, 4 ноября — нерабочий праздничный день (День народного единства)"
    )
    days = [date(2026, 3, 7), date(2026, 3, 8), date(2026, 3, 9)]
    assert (
        calendar_line(days).text
        == "7–9 марта, сб–пн — нерабочие: сб 7 марта, вс 8 марта (Международный женский день)"
    )
    days = [date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)]
    assert calendar_line(days).text == "30 июня – 2 июля, вт–чт — рабочие дни"


def test_seasonality_compares_month_with_yearly_average() -> None:
    months = {month: 100.0 for month in range(1, 13)}
    months[3] = 160.0
    months[7] = 105.0
    seasonality = {"power_loss": months}
    item = prediction(datetime(2026, 3, 2, 9, 0, tzinfo=UTC))

    march = seasonality_line(item, 3, seasonality)
    july = seasonality_line(item, 7, seasonality)

    assert march is not None and march.label == "Сезонность"
    assert march.text == "Март: отключений питания обычно на 52% больше, чем в среднем за месяц"
    assert july is not None and "столько же" in july.text
    assert seasonality_line(prediction(item.prediction_time, device="fan"), 3, seasonality) is None
    assert seasonality_line(item, 3, {}) is None


def test_weather_line_needs_matching_days() -> None:
    weather = [
        {"day": "2026-03-02", "temp_min": -3.2, "temp_max": 4.1, "precipitation_mm": 2.5},
        {"day": "2026-03-03", "temp_min": -1.0, "temp_max": 6.0, "thaw": True},
    ]

    line = weather_line([date(2026, 3, 2), date(2026, 3, 3)], weather)

    assert line is not None
    assert line.text == "-3…+6 °C, осадки 2,5 мм, переход через 0 °C"
    assert weather_line([date(2026, 7, 1)], weather) is None


def test_build_context_skips_missing_sources() -> None:
    item = prediction(datetime(2026, 11, 3, 12, 0, tzinfo=UTC))

    lines = build_context(item, {}, [], "Europe/Moscow")

    assert [line.label for line in lines] == ["Календарь"]
    assert "День народного единства" in lines[0].text


def test_prediction_detail_includes_context(client: TestClient, ml_root: Path) -> None:
    write_scored(ml_root)
    months = {str(month): 10.0 for month in range(1, 13)}
    (ml_root / "results" / "seasonality.json").write_text(
        json.dumps({"monthly_onsets_per_100_channels": {"pump_fault": months}}), encoding="utf-8"
    )
    prediction_id = client.get("/api/v1/predictions").json()[0]["id"]

    detail = client.get(f"/api/v1/predictions/{prediction_id}").json()

    assert [line["label"] for line in detail["context"]] == ["Сезонность", "Календарь"]
    assert "насосов" in detail["context"][0]["text"]
