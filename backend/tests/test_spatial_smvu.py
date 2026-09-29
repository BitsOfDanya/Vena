from fastapi.testclient import TestClient


def test_spatial_demo_seeded_and_wkt_import(client: TestClient, auth_users) -> None:

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

    files = [path for path in tmp_path.iterdir() if path.suffix == ".jsonl"]
    assert len(files) == 1
    records = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert records[0]["ts"] == "2026-07-01T09:00:00"
    # An offset is converted to the journal's local time (Europe/Moscow, UTC+3).
    assert records[1]["ts"] == "2026-07-01T09:05:00"
    assert records[1]["alarm"] is False
