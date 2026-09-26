from fastapi.testclient import TestClient


def test_spatial_demo_seeded_and_wkt_import(client: TestClient, monkeypatch) -> None:
    from app.core.config import get_settings

    status = client.get("/api/v1/spatial/status").json()
    assert status["configured"] is True
    assert status["asset_count"] >= 1

    collection = client.get("/api/v1/spatial").json()
    assert collection["type"] == "FeatureCollection"
    assert collection["source"] == "demo_spatial"
    assert any(
        feature.get("properties", {}).get("asset_id") == "P-0142"
        for feature in collection["features"]
    )

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys_json", '{"admin-secret":"admin"}')
    headers = {"X-API-Key": "admin-secret"}

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
