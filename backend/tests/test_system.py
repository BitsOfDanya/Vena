from fastapi.testclient import TestClient


def test_notices_report_only_real_problems(client: TestClient) -> None:
    response = client.get("/api/v1/system/notices")

    assert response.status_code == 200
    assert all(notice["id"] != "model-unavailable" for notice in response.json())


def test_components_report_email_state(client: TestClient) -> None:
    body = client.get("/api/v1/system/components").json()

    assert body["api"] == "ok"
    assert body["notification_service"] == "not_configured"
    assert body["spatial"] == "not_configured"


def test_components_expose_prediction_freshness(client: TestClient) -> None:
    body = client.get("/api/v1/system/components").json()

    assert body["ml"] in {"ok", "stale", "unavailable"}
    assert "last_prediction_at" in body


def test_email_status_is_not_configured(client: TestClient) -> None:
    body = client.get("/api/v1/integrations/email/status").json()

    assert body == {"configured": False, "provider": "none", "from_address": None}
