from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient


def _payload(status: str = "planned") -> dict:
    return {
        "asset_id": "P-0142",
        "kind": "inspect",
        "reason": "rising event rate",
        "priority": "high",
        "recommended_at": (datetime.now(tz=UTC) + timedelta(hours=24)).isoformat(),
        "assignee": "Бригада А",
        "source": "vena_forecast",
        "source_detail": "Pump72",
        "status": status,
    }


def test_action_lifecycle_and_history(client: TestClient) -> None:
    created = client.post("/api/v1/actions", json=_payload("suggested"))
    assert created.status_code == 201
    action_id = created.json()["id"]

    approved = client.post(f"/api/v1/actions/{action_id}/approve").json()
    assert approved["status"] == "planned"

    assigned = client.post(
        f"/api/v1/actions/{action_id}/assign", json={"assignee": "Бригада Б"}
    ).json()
    assert assigned["status"] == "assigned"
    assert assigned["assignee"] == "Бригада Б"

    started = client.post(f"/api/v1/actions/{action_id}/start").json()
    assert started["status"] == "in_progress"

    completed = client.post(
        f"/api/v1/actions/{action_id}/result",
        json={"outcome": "confirmed_issue", "note": "contactor replaced"},
    ).json()
    assert completed["status"] == "completed"
    assert completed["result_outcome"] == "confirmed_issue"
    assert completed["completed_at"] is not None

    events = [item["event_type"] for item in completed["history"]]
    assert events[0] == "suggested"
    assert "approved" in events
    assert "assigned" in events
    assert "started" in events
    assert "result_recorded" in events


def test_invalid_transition_returns_409(client: TestClient) -> None:
    action_id = client.post("/api/v1/actions", json=_payload("planned")).json()["id"]

    response = client.post(f"/api/v1/actions/{action_id}/approve")

    assert response.status_code == 409


def test_dismiss_suggested_action(client: TestClient) -> None:
    action_id = client.post("/api/v1/actions", json=_payload("suggested")).json()["id"]

    dismissed = client.post(f"/api/v1/actions/{action_id}/dismiss").json()

    assert dismissed["status"] == "dismissed"


def test_action_persists_between_requests(client: TestClient) -> None:
    action_id = client.post("/api/v1/actions", json=_payload("planned")).json()["id"]

    listed = client.get("/api/v1/actions", params={"asset_id": "P-0142"}).json()

    assert [item["id"] for item in listed] == [action_id]
