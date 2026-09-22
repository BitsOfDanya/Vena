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
    assert second["processed"] is False
    assert second["detail"] == "snapshot already processed"
    assert len(client.get("/api/v1/notifications").json()) == 2


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

    assert [item["title"] for item in situations] == ["100", "200"]
    assert situations[0]["severity"] == "critical"
    assert situations[0]["risk_score"] == pytest.approx(0.995)
    assert situations[0]["forecast_horizon"] == 72
    assert situations[0]["primary_reason"].startswith("Events, 24h")


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
