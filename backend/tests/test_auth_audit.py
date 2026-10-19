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


def test_sign_in_events_are_audited_without_passwords(client: TestClient, auth_users) -> None:
    for login in ["admin", "nobody"]:
        failed = client.post(
            "/api/v1/auth/login", json={"login": login, "password": "attempted-secret-42"}
        )
        assert failed.status_code == 401
    token = client.post(
        "/api/v1/auth/login",
        headers={"X-Forwarded-For": "203.0.113.7"},
        json={"login": "viewer", "password": "test-password-123"},
    ).json()["access_token"]
    client.cookies.clear()
    bearer = {"Authorization": "Bearer " + token}
    assert client.post("/api/v1/auth/logout", headers=bearer).status_code == 200
    changed = client.post(
        "/api/v1/auth/password",
        headers=auth_users["dispatcher"],
        json={"current_password": "test-password-123", "new_password": "updated-password-123"},
    )
    assert changed.status_code == 200

    entries = client.get("/api/v1/audit", headers=auth_users["admin"]).json()
    events = {(e["action"], e["actor"]): e for e in entries}
    assert events[("auth.login_failed", "admin")]["detail"] == "reason=password"
    assert events[("auth.login_failed", "admin")]["resource_type"] == "user"
    assert events[("auth.login_failed", "nobody")]["detail"] == "reason=unknown_login"
    assert events[("auth.login_failed", "nobody")]["resource_id"] == ""
    assert ("auth.login", "viewer") in events
    assert ("auth.logout", "viewer") in events
    assert ("auth.password_change", "dispatcher") in events
    assert all(e["ip"] == "testclient" for e in entries if e["action"].startswith("auth."))
    assert "attempted-secret-42" not in str(entries)


def test_forwarded_address_trusted_only_from_proxy(monkeypatch) -> None:
    from starlette.requests import Request

    from app.core.config import get_settings
    from app.core.security import client_ip

    settings = get_settings()

    def request(peer: str, forwarded: str) -> Request:
        headers = [(b"x-forwarded-for", forwarded.encode())]
        return Request({"type": "http", "client": (peer, 40000), "headers": headers})

    monkeypatch.setattr(settings, "trusted_proxies", [])
    assert client_ip(request("10.0.0.5", "198.51.100.1"), settings) == "10.0.0.5"
    monkeypatch.setattr(settings, "trusted_proxies", ["10.0.0.0/8"])
    assert client_ip(request("10.0.0.5", "198.51.100.1, 203.0.113.9"), settings) == "203.0.113.9"
    assert client_ip(request("10.0.0.5", "not-an-address"), settings) == "10.0.0.5"
    assert client_ip(request("192.0.2.1", "203.0.113.9"), settings) == "192.0.2.1"
    monkeypatch.setattr(settings, "trusted_proxies", ["localhost"])
    assert client_ip(request("127.0.0.1", "203.0.113.9"), settings) == "203.0.113.9"


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
