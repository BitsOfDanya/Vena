from fastapi.testclient import TestClient


def test_spatial_requires_explicit_import_or_demo_request(client: TestClient, auth_users) -> None:

    empty = client.get("/api/v1/spatial/status", headers=auth_users["admin"]).json()
    assert empty["configured"] is False
    assert client.get("/api/v1/spatial", headers=auth_users["admin"]).status_code == 404
    assert client.post("/api/v1/spatial/demo", headers=auth_users["admin"]).status_code == 200
    status = client.get("/api/v1/spatial/status", headers=auth_users["admin"]).json()
    assert status["configured"] is True
    assert status["asset_count"] >= 1

    collection = client.get("/api/v1/spatial", headers=auth_users["admin"]).json()
    assert collection["type"] == "FeatureCollection"
    assert collection["source"] == "demo_spatial"
    assert any(
        feature.get("properties", {}).get("asset_id") == "P-0142"
        for feature in collection["features"]
    )

    headers = auth_users["admin"]

    wkt = client.put(
        "/api/v1/spatial/wkt",
        headers=headers,
        json={"points": [{"asset_id": "P-0142", "wkt": "POINT (37.64 55.75)"}]},
    )
    assert wkt.status_code == 200
    body = wkt.json()
    assets = [
        feature
        for feature in body["features"]
        if feature.get("properties", {}).get("kind") == "asset"
    ]
    assert len(assets) == 1
    assert assets[0]["geometry"]["coordinates"] == [37.64, 55.75]


def test_smvu_ingest_marks_fresh(client: TestClient) -> None:
    empty = client.get("/api/v1/smvu/status").json()
    assert empty["configured"] is False

    accepted = client.post(
        "/api/v1/smvu/events",
        json={"batch_id": "batch-1", "event_count": 42, "detail": "stand feed"},
    )
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["configured"] is True
    assert body["fresh"] is True
    assert body["last_event_count"] == 42


def test_smvu_events_are_spooled_for_the_stream(client: TestClient, monkeypatch, tmp_path) -> None:
    import json

    from app.core.config import get_settings

    events = [
        {
            "event_id": "1",
            "channel_id": "96463",
            "ts": "2026-07-01T09:00:00",
            "value": "Неисправен",
            "alarm": True,
        },
        {
            "event_id": "2",
            "channel_id": "96463",
            "ts": "2026-07-01T06:05:00+00:00",
            "value": "Норма",
        },
    ]
    unconfigured = client.post(
        "/api/v1/smvu/events", json={"batch_id": "b-0", "event_count": 2, "events": events}
    )
    assert unconfigured.status_code == 503

    monkeypatch.setattr(get_settings(), "inbox_dir", tmp_path)
    accepted = client.post(
        "/api/v1/smvu/events", json={"batch_id": "b-1", "event_count": 0, "events": events}
    )
    assert accepted.status_code == 202
    assert accepted.json()["last_event_count"] == 2

    from app.db.session import SessionLocal
    from app.domain.imports import publish_pending

    with SessionLocal() as session:
        publish_pending(session, get_settings())
    files = [path for path in tmp_path.iterdir() if path.suffix == ".jsonl"]
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["ts"] == "2026-07-01T09:00:00"
    assert records[1]["ts"] == "2026-07-01T09:05:00"
    assert records[1]["alarm"] is False


def test_production_rejects_demo_map(client, auth_users, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "environment", "production")
    response = client.post("/api/v1/spatial/demo", headers=auth_users["admin"])
    assert response.status_code == 409
    assert (
        client.get("/api/v1/spatial/status", headers=auth_users["admin"]).json()["configured"]
        is False
    )


def test_component_status_tracks_imported_map_and_event_time(client, auth_users):
    result = client.put(
        "/api/v1/spatial/wkt",
        headers=auth_users["admin"],
        json={"points": [{"asset_id": "real-1", "wkt": "POINT (37.6 55.7)"}]},
    )
    assert result.status_code == 200
    client.post(
        "/api/v1/smvu/events",
        headers=auth_users["admin"],
        json={
            "batch_id": "freshness-check",
            "event_count": 1,
            "last_event_at": "2026-09-29T12:00:00Z",
        },
    )
    state = client.get("/api/v1/system/components", headers=auth_users["admin"]).json()
    assert state["spatial"] == "configured"
    from datetime import datetime

    assert datetime.fromisoformat(state["last_event_at"]) == datetime.fromisoformat(
        "2026-09-29T12:00:00+00:00"
    )


def test_stream_events_are_atomic_deduplicated_and_visible(
    client, auth_users, monkeypatch, tmp_path
):
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.domain.imports import publish_pending

    monkeypatch.setattr(get_settings(), "inbox_dir", tmp_path)
    headers = auth_users["dispatcher"]
    event = {
        "event_id": "real-event-1",
        "channel_id": "channel-1",
        "ts": "2026-06-01T12:00:00",
        "value": "Норма",
        "alarm": False,
    }
    body = {"batch_id": "batch-one", "event_count": 1, "events": [event]}
    assert (
        client.post("/api/v1/smvu/events", headers=auth_users["viewer"], json=body).status_code
        == 403
    )
    result = client.post("/api/v1/smvu/events", headers=headers, json=body)
    assert result.status_code == 202
    assert result.json()["last_event_count"] == 1
    again = client.post("/api/v1/smvu/events", headers=headers, json=body)
    assert again.status_code == 202 and again.json()["last_event_count"] == 0
    conflict = {
        **body,
        "events": [{**event, "event_id": "new-event"}, {**event, "value": "Неисправен"}],
    }
    assert client.post("/api/v1/smvu/events", headers=headers, json=conflict).status_code == 409
    feed = client.get("/api/v1/events/recent", headers=auth_users["viewer"]).json()
    assert len(feed["items"]) == 1
    assert feed["items"][0]["value"] == "Норма"
    assert feed["items"][0]["event_id"] == "real-event-1"
    with SessionLocal() as session:
        publish_pending(session, get_settings())
        publish_pending(session, get_settings())
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_stream_outbox_retries_storage_failure(client, auth_users, monkeypatch, tmp_path):
    import pytest
    from sqlalchemy import select

    from app.core.config import get_settings
    from app.db.models import ImportOutbox
    from app.db.session import SessionLocal
    from app.domain import smvu
    from app.domain.imports import publish_pending

    monkeypatch.setattr(get_settings(), "inbox_dir", tmp_path)
    event = {
        "event_id": "retry-1",
        "channel_id": "channel-1",
        "ts": "2026-06-01T12:00:00Z",
        "value": "Норма",
    }
    response = client.post(
        "/api/v1/smvu/events",
        headers=auth_users["dispatcher"],
        json={"batch_id": "retry", "event_count": 1, "events": [event]},
    )
    assert response.status_code == 202
    with monkeypatch.context() as patched:

        def fail(*args, **kwargs):
            raise OSError("temporary storage failure")

        patched.setattr(smvu, "spool_events", fail)
        with SessionLocal() as db, pytest.raises(OSError):
            publish_pending(db, get_settings())
    with SessionLocal() as db:
        pending = db.scalar(select(ImportOutbox))
        assert pending.delivered_at is None
        publish_pending(db, get_settings())
        assert pending.delivered_at is not None
    assert len(list(tmp_path.glob("*.jsonl"))) == 1
