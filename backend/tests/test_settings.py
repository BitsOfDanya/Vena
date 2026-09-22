from fastapi.testclient import TestClient


def test_default_rules_and_recipients(client: TestClient) -> None:
    body = client.get("/api/v1/settings/notifications").json()

    assert {rule["id"] for rule in body["rules"]} >= {
        "critical_risk",
        "new_pattern",
        "action_overdue",
    }
    assert {group["id"] for group in body["recipients"]} == {
        "dispatcher_team",
        "maintenance_team",
        "management",
    }
    assert [channel for channel in body["channels"] if channel["id"] == "email"][0][
        "state"
    ] == "not_configured"


def test_settings_are_persisted(client: TestClient) -> None:
    current = client.get("/api/v1/settings/notifications").json()
    current["recipients"][0]["emails"] = ["dispatcher@example.com"]

    updated = client.put(
        "/api/v1/settings/notifications",
        json={"recipients": current["recipients"]},
    )

    assert updated.status_code == 200
    stored = client.get("/api/v1/settings/notifications").json()
    assert stored["recipients"][0]["emails"] == ["dispatcher@example.com"]


def test_invalid_email_is_rejected(client: TestClient) -> None:
    response = client.put(
        "/api/v1/settings/notifications",
        json={
            "recipients": [
                {"id": "dispatcher_team", "name": "Dispatcher", "emails": ["not-an-email"]}
            ]
        },
    )

    assert response.status_code == 422
