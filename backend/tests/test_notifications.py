from fastapi.testclient import TestClient


def _create(client: TestClient, severity: str = "critical") -> str:
    response = client.post(
        "/api/v1/notifications",
        json={
            "type": "risk",
            "severity": severity,
            "title": "P-0142 risk",
            "description": "rising event rate",
            "asset_id": "P-0142",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_notification_lifecycle(client: TestClient) -> None:
    notification_id = _create(client)

    acknowledged = client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "acknowledged"}
    )
    assert acknowledged.status_code == 200
    body = acknowledged.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None
    assert body["read_at"] is not None

    resolved = client.patch(f"/api/v1/notifications/{notification_id}", json={"status": "resolved"})
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


def test_invalid_transition_is_rejected(client: TestClient) -> None:
    notification_id = _create(client)
    client.patch(f"/api/v1/notifications/{notification_id}", json={"status": "resolved"})

    response = client.patch(
        f"/api/v1/notifications/{notification_id}", json={"status": "acknowledged"}
    )

    assert response.status_code == 409


def test_acknowledge_survives_new_client(client: TestClient) -> None:
    notification_id = _create(client)
    client.patch(f"/api/v1/notifications/{notification_id}", json={"status": "acknowledged"})

    listed = client.get("/api/v1/notifications", params={"status": "acknowledged"}).json()

    assert [item["id"] for item in listed] == [notification_id]


def test_filters(client: TestClient) -> None:
    _create(client, "critical")
    _create(client, "attention")

    critical = client.get("/api/v1/notifications", params={"severity": "critical"}).json()

    assert len(critical) == 1
    assert critical[0]["severity"] == "critical"


def test_test_email_requires_configuration(client: TestClient) -> None:
    response = client.post(
        "/api/v1/notifications/test", json={"recipient": "dispatcher@example.com"}
    )

    assert response.status_code == 409
    assert "не настроена" in response.json()["detail"]
