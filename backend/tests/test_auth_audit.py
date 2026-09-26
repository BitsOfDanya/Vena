from fastapi.testclient import TestClient


def test_auth_me_disabled_by_default(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert response.json()["auth_method"] == "disabled"


def test_auth_rejects_without_key_when_enabled(client: TestClient, monkeypatch) -> None:
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "api_keys_json", '{"admin-secret":"admin"}')

    assert client.get("/api/v1/auth/me").status_code == 401
    ok = client.get("/api/v1/auth/me", headers={"X-API-Key": "admin-secret"})
    assert ok.status_code == 200
    assert ok.json()["role"] == "admin"


def test_audit_requires_admin_and_records_action_mutations(
    client: TestClient, monkeypatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(
        settings,
        "api_keys_json",
        '{"admin-secret":"admin","dispatch-secret":"dispatcher","view-secret":"viewer"}',
    )

    headers = {"X-API-Key": "dispatch-secret"}
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

    denied = client.get("/api/v1/audit", headers={"X-API-Key": "view-secret"})
    assert denied.status_code == 403

    entries = client.get("/api/v1/audit", headers={"X-API-Key": "admin-secret"}).json()
    assert any(entry["action"] == "action.create" for entry in entries)
