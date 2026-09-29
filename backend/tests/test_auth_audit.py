from fastapi.testclient import TestClient


def test_audit_requires_admin_and_records_action_mutations(client: TestClient, auth_users) -> None:
    from datetime import UTC, datetime, timedelta

    headers = auth_users["dispatcher"]
    created = client.post(
        "/api/v1/actions",
        headers=headers,
        json={
            "asset_id": "P-0142",
            "kind": "inspect",
            "reason": "audit test",
            "priority": "high",
            "recommended_at": (datetime.now(tz=UTC) + timedelta(hours=24)).isoformat(),
            "assignee": "Бригада А",
            "note": "",
            "source": "manual",
            "status": "planned",
        },
    )
    assert created.status_code == 201

    denied = client.get("/api/v1/audit", headers=auth_users["viewer"])
    assert denied.status_code == 403

    entries = client.get("/api/v1/audit", headers=auth_users["admin"]).json()
    assert any(entry["action"] == "action.create" for entry in entries)


def test_viewer_cannot_mutate_actions(client: TestClient, auth_users) -> None:
    from datetime import UTC, datetime, timedelta

    denied = client.post(
        "/api/v1/actions",
        headers=auth_users["viewer"],
        json={
            "asset_id": "P-0142",
            "kind": "inspect",
            "reason": "should fail",
            "priority": "low",
            "recommended_at": (datetime.now(tz=UTC) + timedelta(hours=24)).isoformat(),
            "assignee": "",
            "note": "",
            "source": "manual",
            "status": "planned",
        },
    )
    assert denied.status_code == 403
