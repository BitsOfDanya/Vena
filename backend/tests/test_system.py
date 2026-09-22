from fastapi.testclient import TestClient


def test_notices_are_empty_when_ml_is_mounted(client: TestClient) -> None:
    response = client.get("/api/v1/system/notices")

    assert response.status_code == 200
    assert response.json() == []


def test_components_report_email_state(client: TestClient) -> None:
    body = client.get("/api/v1/system/components").json()

    assert body["api"] == "ok"
    assert body["notification_service"] == "not_configured"
    assert body["spatial"] == "not_configured"


def test_situations_combine_notifications_and_actions(client: TestClient) -> None:
    client.post(
        "/api/v1/notifications",
        json={
            "type": "risk",
            "severity": "critical",
            "title": "P-0142 risk",
            "description": "rising event rate",
            "asset_id": "P-0142",
        },
    )

    situations = client.get("/api/v1/situations").json()
    assert len(situations) == 1
    assert situations[0]["status"] == "new"

    client.post(
        "/api/v1/actions",
        json={
            "asset_id": "P-0142",
            "reason": "inspect",
            "priority": "high",
            "recommended_at": "2030-01-01T00:00:00+00:00",
            "status": "planned",
        },
    )

    updated = client.get("/api/v1/situations").json()
    assert updated[0]["status"] == "action_created"
    assert updated[0]["open_action_id"] is not None


def test_email_status_is_not_configured(client: TestClient) -> None:
    body = client.get("/api/v1/integrations/email/status").json()

    assert body == {"configured": False, "provider": "none", "from_address": None}
