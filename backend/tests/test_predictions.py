import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.domain.predictions import reset_prediction_source

CONFIG = {
    "device": "pump",
    "horizon": "72h",
    "model": {
        "model_name": "logistic_regression",
        "horizon_hours": 72,
        "calibrated": False,
        "risk_level_thresholds": {"critical": 0.99, "high": 0.9, "medium": 0.8},
    },
}


def write_snapshot(
    root: Path, prediction_time: datetime, rows: list[dict], snapshot_id: str = "snap-1"
) -> None:
    models = root / "configs" / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "pump_72h.json").write_text(json.dumps(CONFIG), encoding="utf-8")
    (root / "results").mkdir(parents=True, exist_ok=True)
    (root / "results" / "directions.json").write_text("[]", encoding="utf-8")
    predictions = root / "results" / "predictions"
    predictions.mkdir(parents=True, exist_ok=True)
    payload = {
        "snapshot_id": snapshot_id,
        "generated_at": prediction_time.isoformat(),
        "prediction_time": prediction_time.isoformat(),
        "models": {"pump_72h": {"version": "2026-09-16", "horizon_hours": 72, "calibrated": False}},
        "predictions": rows,
    }
    (predictions / "snapshot.json").write_text(json.dumps(payload), encoding="utf-8")


def row(channel: str, score: float, level: str) -> dict:
    return {
        "channel_id": channel,
        "device_type": "pump",
        "model_id": "pump_72h",
        "model_version": "2026-09-16",
        "horizon_hours": 72,
        "score": score,
        "score_type": "risk_score",
        "model_risk_level": level,
        "last_event_at": "2026-06-30T23:00:00",
        "factors": {"events_24h": 12.0, "failures_30d": 2.0},
        "sensor_type": "Состояние насоса",
        "system_type": "Водоотведение",
    }


@pytest.fixture()
def ml_root(tmp_path: Path):
    settings = get_settings()
    original = settings.ml_dir
    settings.ml_dir = tmp_path
    reset_prediction_source()
    yield tmp_path
    settings.ml_dir = original
    reset_prediction_source()


def test_snapshot_parsing_maps_levels_and_score_type(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root,
        datetime.now(tz=UTC),
        [
            row("100", 0.995, "critical"),
            row("200", 0.91, "high"),
            row("300", 0.82, "medium"),
            row("400", 0.1, "low"),
        ],
    )

    items = client.get("/api/v1/predictions", params={"limit": 10}).json()

    levels = {item["asset_id"]: item["risk_level"] for item in items}
    assert levels == {"100": "critical", "200": "attention", "300": "observe", "400": "normal"}
    assert {item["score_type"] for item in items} == {"risk_score"}
    assert all("probability" not in item for item in items)


def test_calibrated_flag_changes_score_type(client: TestClient, ml_root: Path) -> None:
    calibrated = row("100", 0.4, "low")
    calibrated["score_type"] = "calibrated_probability"
    write_snapshot(ml_root, datetime.now(tz=UTC), [calibrated])

    item = client.get("/api/v1/predictions").json()[0]

    assert item["score_type"] == "calibrated_probability"


def test_predictions_unavailable_without_snapshot(client: TestClient, ml_root: Path) -> None:
    response = client.get("/api/v1/predictions")

    assert response.status_code == 503
    notices = client.get("/api/v1/system/notices").json()
    assert "predictions-unavailable" in [notice["id"] for notice in notices]
    assert client.get("/api/v1/situations").json() == []


def test_stale_snapshot_raises_notice_but_keeps_api_healthy(
    client: TestClient, ml_root: Path
) -> None:
    write_snapshot(
        ml_root, datetime.now(tz=UTC) - timedelta(days=5), [row("100", 0.995, "critical")]
    )

    status = client.get("/api/v1/predictions/snapshot").json()
    notices = client.get("/api/v1/system/notices").json()
    components = client.get("/api/v1/system/components").json()

    assert status["stale"] is True
    assert "predictions-stale" in [notice["id"] for notice in notices]
    stale = next(notice for notice in notices if notice["id"] == "predictions-stale")
    assert stale["severity"] == "info"
    assert "Демонстрационный" in stale["title"]
    assert components["api"] == "ok"
    assert components["ml"] == "stale"
    assert client.get("/api/v1/health").json()["status"] == "ok"


def test_refresh_is_idempotent_and_creates_notifications(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical"), row("200", 0.91, "high")]
    )

    first = client.post("/api/v1/predictions/refresh").json()
    second = client.post("/api/v1/predictions/refresh").json()

    assert first["processed"] is True
    assert first["notifications_created"] == 2
    assert first["actions_created"] == 2
    assert second["processed"] is False
    assert second["detail"] == "snapshot already processed"
    assert len(client.get("/api/v1/notifications").json()) == 2
    suggested = client.get("/api/v1/actions", params={"status": "suggested"}).json()
    assert len(suggested) == 2
    assert all(item["source"] == "vena_forecast" for item in suggested)


def test_cooldown_suppresses_repeated_notifications(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical")], snapshot_id="snap-1"
    )
    client.post("/api/v1/predictions/refresh")

    write_snapshot(
        ml_root, datetime.now(tz=UTC), [row("100", 0.996, "critical")], snapshot_id="snap-2"
    )
    reset_prediction_source()
    second = client.post("/api/v1/predictions/refresh").json()

    assert second["processed"] is True
    assert second["notifications_created"] == 0
    assert len(client.get("/api/v1/notifications").json()) == 1


def test_history_and_delta_between_snapshots(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root,
        datetime.now(tz=UTC) - timedelta(hours=2),
        [row("100", 0.80, "medium")],
        snapshot_id="snap-1",
    )
    client.post("/api/v1/predictions/refresh")
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.93, "high")], snapshot_id="snap-2")
    reset_prediction_source()
    client.post("/api/v1/predictions/refresh")

    history = client.get("/api/v1/assets/100/predictions").json()
    latest = client.get("/api/v1/assets/100/prediction").json()

    assert len(history) == 2
    assert {point["snapshot_id"] for point in history} == {"snap-1", "snap-2"}
    assert latest["score"] == pytest.approx(0.93)


def test_situations_are_built_from_predictions(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical"), row("200", 0.91, "high")]
    )

    situations = client.get("/api/v1/situations").json()

    assert [item["title"] for item in situations] == ["Подтопление · 100", "Подтопление · 200"]
    assert situations[0]["scenario"] == "flooding"
    assert situations[0]["severity"] == "critical"
    assert situations[0]["risk_score"] == pytest.approx(0.995)
    assert situations[0]["forecast_horizon"] == 72
    assert situations[0]["primary_reason"].startswith("Событий за 24 ч")


def test_prediction_detail_links_action_and_notification(client: TestClient, ml_root: Path) -> None:
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical")])
    client.post("/api/v1/predictions/refresh")
    prediction = client.get("/api/v1/predictions").json()[0]
    client.post(
        "/api/v1/actions",
        json={
            "asset_id": "100",
            "reason": "inspect",
            "priority": "high",
            "recommended_at": "2030-01-01T00:00:00+00:00",
            "source": "vena_forecast",
            "source_prediction_id": prediction["id"],
            "source_model_id": prediction["model_id"],
            "source_prediction_time": prediction["prediction_time"],
            "source_score": prediction["score"],
            "source_horizon_hours": prediction["horizon_hours"],
        },
    )

    detail = client.get(f"/api/v1/predictions/{prediction['id']}").json()

    assert detail["open_action_id"] is not None
    assert detail["notification_id"] is not None
    assert detail["model"]["calibrated"] is False


def test_feedback_export_links_prediction_action_and_result(
    client: TestClient, ml_root: Path
) -> None:
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical")])
    prediction = client.get("/api/v1/predictions").json()[0]
    action = client.post(
        "/api/v1/actions",
        json={
            "asset_id": "100",
            "reason": "inspect",
            "priority": "high",
            "recommended_at": "2030-01-01T00:00:00+00:00",
            "source": "vena_forecast",
            "source_prediction_id": prediction["id"],
            "source_model_id": prediction["model_id"],
            "source_prediction_time": prediction["prediction_time"],
            "source_score": prediction["score"],
            "source_horizon_hours": prediction["horizon_hours"],
            "status": "planned",
        },
    ).json()
    client.post(f"/api/v1/actions/{action['id']}/assign", json={"assignee": "Бригада А"})
    client.post(f"/api/v1/actions/{action['id']}/start")
    client.post(
        f"/api/v1/actions/{action['id']}/result",
        json={"outcome": "confirmed_issue", "note": "checked"},
    )

    feedback = client.get("/api/v1/ml/feedback").json()

    assert len(feedback) == 1
    assert feedback[0]["prediction_id"] == prediction["id"]
    assert feedback[0]["model_id"] == "pump_72h"
    assert feedback[0]["action_result"] == "confirmed_issue"
    assert feedback[0]["completed_at"] is not None


def tagged(channel: str, score: float, level: str, tag: str, device: str = "phase") -> dict:
    return {
        **row(channel, score, level),
        "device_type": device,
        "model_id": "pump_72h",
        "tag": tag,
    }


def test_channels_of_one_location_form_one_incident(client: TestClient, ml_root: Path) -> None:
    write_snapshot(
        ml_root,
        datetime.now(tz=UTC),
        [
            tagged("11", 0.97, "critical", "16-2.1.1.4.22."),
            tagged("12", 0.96, "critical", "16-2.1.1.4.23."),
            tagged("13", 0.95, "critical", "16-2.1.1.1.5."),
            tagged("21", 0.93, "high", "798-2.3.1.3.19."),
        ],
    )

    situations = client.get("/api/v1/situations").json()
    refresh = client.post("/api/v1/predictions/refresh").json()
    prediction = client.get("/api/v1/assets/11/prediction").json()

    assert [item["asset_count"] for item in situations] == [3, 1]
    assert situations[0]["asset_ids"] == ["11", "12", "13"]
    assert situations[0]["title"] == "Потеря питания · Объект 16 · 2.1.1"
    assert refresh["notifications_created"] == 2
    assert refresh["actions_created"] == 2
    assert prediction["scenario"] == "power_loss"
    assert prediction["location"] == "Объект 16 · 2.1.1"


def test_dismiss_records_catalogue_reason_in_journal(client: TestClient, ml_root: Path) -> None:
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical")])
    client.post("/api/v1/predictions/refresh")
    action = client.get("/api/v1/actions", params={"status": "suggested"}).json()[0]

    reasons = client.get("/api/v1/journal/reasons").json()
    dismissed = client.post(
        f"/api/v1/actions/{action['id']}/dismiss",
        json={"reason": "false_alarm", "note": "камера 12"},
    ).json()
    journal = client.get("/api/v1/journal").json()
    summary = client.get("/api/v1/journal/summary").json()

    assert "false_alarm" in {item["code"] for item in reasons}
    assert dismissed["status"] == "dismissed"
    assert dismissed["result_outcome"] == "false_or_irrelevant_signal"
    assert dismissed["result_note"] == "Ложное срабатывание. камера 12"
    assert journal[0]["decision"] == "no_dispatch"
    assert journal[0]["scenario"] == "flooding"
    assert summary["by_scenario"][0]["rejected"] == 1
    assert summary["by_scenario"][0]["confirmation_rate"] == 0.0


def test_alarm_and_access_sections_are_served(client: TestClient, ml_root: Path) -> None:
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.5, "low")])
    path = ml_root / "results" / "predictions" / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["alarms"] = [
        {
            "channel_id": "7",
            "ts": "2026-06-30T10:00:00",
            "sensor_type": "Датчик дыма",
            "corroboration_probability": 0.12,
            "needs_verification": True,
            "tag": "16-2.1.1.4.22.",
            "name": "ДИП ПК12",
        },
        {
            "channel_id": "8",
            "ts": "2026-06-30T11:00:00",
            "sensor_type": "Газовый датчик",
            "corroboration_probability": 0.93,
            "needs_verification": False,
        },
    ]
    payload["access_events"] = [
        {
            "channel_id": "9",
            "ts": "2026-06-29T02:00:00",
            "sensor_type": "КД Люк",
            "object": "16",
            "access_index": 0.8,
            "night": True,
            "chain": False,
            "tag": "16-1.1.66.1.",
        }
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    alarms = client.get("/api/v1/alarms").json()
    false_alarms = client.get("/api/v1/alarms", params={"needs_verification": True}).json()
    access = client.get("/api/v1/access-events").json()

    assert [item["channel_id"] for item in alarms] == ["8", "7"]
    assert [item["channel_id"] for item in false_alarms] == ["7"]
    assert false_alarms[0]["location"] == "Объект 16 · 2.1.1"
    assert access[0]["access_index"] == pytest.approx(0.8)
    assert access[0]["location"] == "Объект 16 · 1.1.66"


def test_drivers_and_location_probability_reach_situations(
    client: TestClient, ml_root: Path
) -> None:
    rows = [
        {
            **tagged("11", 0.83, "critical", "16-2.1.1.4.22."),
            "score_type": "calibrated_probability",
            "drivers": [
                {
                    "feature": "failures_1d",
                    "label": "Эпизодов за 1 сут",
                    "value": 3.0,
                    "contribution": 0.4,
                }
            ],
        },
        {
            **tagged("12", 0.61, "critical", "16-2.1.1.4.23."),
            "score_type": "calibrated_probability",
        },
    ]
    write_snapshot(ml_root, datetime.now(tz=UTC), rows)
    path = ml_root / "results" / "predictions" / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["incidents"] = [
        {"location_group": "16-2.1.1", "scenario": "power_loss", "probability": 0.57, "channels": 2}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    prediction = client.get("/api/v1/assets/11/prediction").json()
    situation = client.get("/api/v1/situations").json()[0]

    assert prediction["drivers"][0]["label"] == "Эпизодов за 1 сут"
    assert situation["primary_reason"] == "Эпизодов за 1 сут: 3"
    assert situation["incident_probability"] == pytest.approx(0.83)
    payload["incidents"][0]["probability"] = 0.95
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert client.get("/api/v1/situations").json()[0]["incident_probability"] == pytest.approx(0.95)
    assert "83%" in situation["summary"]
    assert "Риск локации 83%" in situation["summary"]


def test_ml_reports_are_whitelisted(client: TestClient, ml_root: Path) -> None:
    (ml_root / "results").mkdir(parents=True, exist_ok=True)
    (ml_root / "results" / "seasonality.json").write_text(
        '{"seasonal_share": {}}', encoding="utf-8"
    )

    assert client.get("/api/v1/ml/reports/seasonality").json() == {"seasonal_share": {}}
    assert client.get("/api/v1/ml/reports/directions").status_code == 404
    assert client.get("/api/v1/ml/reports/..%2Fsecret").status_code == 404


def test_stream_info_and_prospective_report(client: TestClient, ml_root: Path) -> None:
    write_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.5, "low")])
    path = ml_root / "results" / "predictions" / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["stream"] = {
        "events": 12,
        "channels_rescored": 3,
        "received_at": "2026-07-01T09:00:00Z",
        "published_at": "2026-07-01T09:00:04Z",
        "latency_seconds": 4.2,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert client.get("/api/v1/ml/prospective").status_code == 404
    (ml_root / "results" / "predictions" / "prospective.json").write_text(
        json.dumps({"start": "2026-06-30T23:59:06", "models": {}}), encoding="utf-8"
    )

    assert client.get("/api/v1/predictions/snapshot").json()["stream"]["latency_seconds"] == 4.2
    assert client.get("/api/v1/ml/prospective").json()["models"] == {}


def _snapshot_with_sections(ml_root: Path) -> None:
    rows = [
        {
            **tagged("11", 0.83, "critical", "16-2.1.1.4.22."),
            "horizon_hours": 24,
            "model_id": "phase_24h",
            "score_type": "calibrated_probability",
            "name": "ФАНС1 ПК300",
            "object_id": 5567,
            "drivers": [
                {
                    "feature": "failures_1d",
                    "label": "Эпизодов за 1 сут",
                    "value": 3.0,
                    "contribution": 0.4,
                }
            ],
        },
        {
            **tagged("21", 0.10, "low", "16-2.1.1.4.30.", device="smoke"),
            "horizon_hours": 24,
            "model_id": "smoke_24h",
            "score_type": "calibrated_probability",
        },
        {
            **tagged("31", 0.05, "low", "798-2.3.1.3.19."),
            "horizon_hours": 24,
            "model_id": "phase_24h",
            "score_type": "calibrated_probability",
        },
    ]
    write_snapshot(ml_root, datetime.now(tz=UTC), rows)
    path = ml_root / "results" / "predictions" / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["location_history"] = {
        "16-2.1.1": {
            "phase": {
                "episodes_365d": 40,
                "channels": 5,
                "last_episode_at": "2026-06-30T15:34:17",
                "median_duration_minutes": 0.0,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    (ml_root / "configs" / "recommendations.json").write_text(
        json.dumps(
            {
                "note": "Сверить с РТЭК",
                "scenarios": {
                    "power_loss": {"title": "Проверить питание", "actions": ["Проверить ввод"]}
                },
                "drivers": {"failures_1d": "Сбои повторяются"},
                "feeders": [
                    {
                        "pattern": "ФАНС",
                        "kind": "Фидер насосной станции",
                        "scenario": "flooding",
                        "consequence": "Насосы без питания",
                        "action": "Проверить уровень в приямке",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_situation_explains_the_incident(client: TestClient, ml_root: Path) -> None:
    _snapshot_with_sections(ml_root)

    situation = client.get("/api/v1/situations").json()[0]

    assert situation["recommendation"]["title"] == "Проверить питание"
    assert situation["recommendation"]["hint"] == "Сбои повторяются"
    assert situation["history"]["episodes_365d"] == 40
    assert situation["health_index"] == 15
    assert situation["recommendation"]["feeder"] == "Фидер насосной станции"
    assert situation["recommendation"]["consequence"] == "Насосы без питания"
    assert situation["recommendation"]["actions"][0] == "Проверить уровень в приямке"
    assert situation["location"] == "Объект 5567 · 16-2.1.1"


def test_asset_tree_effect_and_report(client: TestClient, ml_root: Path) -> None:
    _snapshot_with_sections(ml_root)

    tree = client.get("/api/v1/assets/tree").json()
    effect = client.get("/api/v1/analytics/effect").json()
    report = client.get("/api/v1/reports/management.xlsx")

    assert [item["object_id"] for item in tree] == ["5567", "798"]
    assert tree[0]["label"] == "Объект 5567"
    assert tree[0]["health_index"] == 15
    assert tree[0]["sections"][0]["channels"][0]["name"] == "ФАНС1 ПК300"
    assert tree[1]["health_index"] == 95
    assert effect["channels_at_risk"] == 1
    assert effect["incidents"] == 1
    assert report.status_code == 200
    assert report.content[:2] == b"PK"


def test_forecast_exchange_formats_and_event_types(client: TestClient, ml_root: Path) -> None:
    _snapshot_with_sections(ml_root)
    (ml_root / "results" / "workload_forecast.json").write_text(
        json.dumps(
            {
                "scenarios": {
                    "power_loss": {
                        "method": "calendar+level",
                        "recent": {"calendar+level": {"week": 0.1}, "last_28_days": {"week": 0.2}},
                        "history": {"last_30_days": 40, "last_365_days": 500},
                        "forecast": [{"day": "2026-07-01", "expected": 3.0}],
                        "next_7_days": {"expected": 21.0, "low": 15.0, "high": 30.0},
                        "backtest": [{"day": "2026-06-30", "actual": 2, "forecast": 2.5}],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    xml = client.get("/api/v1/reports/predictions.xml")
    table = client.get("/api/v1/reports/predictions.csv")
    listing = client.get("/api/v1/analytics/event-types").json()
    types = {item["event_type"]: item for item in listing}

    assert xml.status_code == 200
    assert xml.content.startswith(b"<?xml")
    assert xml.text.count("<prediction>") == len(client.get("/api/v1/predictions").json())
    assert table.text.splitlines()[0].lstrip("\ufeff").startswith("id,asset_id,name")
    power = types["power_loss"]
    assert power["channels_at_risk"] == {"critical": 1}
    assert power["episodes_365d"] == 500
    assert power["forecast"][0]["expected"] == 3.0
    assert power["next_7_days"]["high"] == 30.0
    assert power["week_error"] < power["week_error_baseline"]
    assert types["pump_fault"]["forecast"] == []


def test_health_calibration_interpolates_between_points() -> None:
    from app.domain.health import calibrate

    points = ([0.0, 0.5, 1.0], [0.02, 0.2, 0.5])
    assert calibrate(0.25, points) == pytest.approx(0.11)
    assert calibrate(2.0, points) == 0.5
    assert calibrate(0.3, None) == 0.3
