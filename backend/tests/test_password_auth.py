from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.security import COOKIE_NAME, PASSWORDS
from app.db.models import AuthSession, User
from app.db.seed_users import seed_users
from app.db.session import SessionLocal


def test_email_username_cookie_and_bearer(client, auth_users):
    result = client.post(
        "/api/v1/auth/login", json={"email": " ADMIN@EXAMPLE.COM ", "password": "test-password-123"}
    )
    assert result.status_code == 200
    assert result.json()["user"]["email"] == "admin@example.com"
    assert result.json()["token_type"] == "bearer"
    assert result.json()["expires_in"] == 3600
    cookie = result.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert result.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/auth/me").json()["subject"] == "admin"
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=auth_users["viewer"]).json()["role"] == "viewer"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": "vena-admin"}).status_code == 401


def test_wrong_password_and_unknown_user_match(client, auth_users):
    results = [
        client.post("/api/v1/auth/login", json={"email": name, "password": "bad"})
        for name in ["admin", "missing"]
    ]
    assert [r.status_code for r in results] == [401, 401]
    assert results[0].json() == results[1].json()


def test_expired_tampered_wrong_audience_and_algorithm(client, auth_users):
    settings = get_settings()
    token = auth_users["admin"]["Authorization"].split()[1]
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=["HS256"], audience=settings.jwt_audience
    )
    for changes, key, algorithm in [
        ({"exp": datetime.now(UTC) - timedelta(seconds=1)}, settings.jwt_secret, "HS256"),
        ({}, "another-secret-with-at-least-thirty-two-bytes", "HS256"),
        ({"aud": "wrong"}, settings.jwt_secret, "HS256"),
        ({"iss": "wrong"}, settings.jwt_secret, "HS256"),
        ({"type": "refresh"}, settings.jwt_secret, "HS256"),
        ({}, "", "none"),
    ]:
        invalid = jwt.encode({**payload, **changes}, key, algorithm=algorithm)
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer " + invalid}
            ).status_code
            == 401
        )


def test_logout_revokes_token_and_cookie_csrf(client, auth_users):
    result = client.post(
        "/api/v1/auth/login", json={"login": "admin", "password": "test-password-123"}
    )
    token = result.json()["access_token"]
    assert (
        client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert (
        client.post(
            "/api/v1/auth/logout", headers={"Origin": get_settings().public_url}
        ).status_code
        == 200
    )
    assert COOKIE_NAME not in client.cookies
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"email": "admin", "password": "test-password-123"},
        ).status_code
        == 403
    )


def test_disabled_user_and_role_changes_apply_immediately(client, auth_users):
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.role = "viewer"
    assert client.get("/api/v1/audit", headers=auth_users["admin"]).status_code == 403
    with SessionLocal.begin() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        user.is_active = False
    assert client.get("/api/v1/auth/me", headers=auth_users["admin"]).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "admin", "password": "test-password-123"}
        ).status_code
        == 401
    )


def test_throttling_persists_failed_attempts(client, auth_users, monkeypatch):
    monkeypatch.setattr(get_settings(), "auth_login_limit", 3)
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": "unknown", "password": "wrong"}
            ).status_code
            == 401
        )
    limited = client.post("/api/v1/auth/login", json={"email": "unknown", "password": "wrong"})
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_password_change_revokes_all_sessions(client, auth_users):
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=auth_users["admin"],
            json={"current_password": "wrong", "new_password": "updated-password-123"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=auth_users["admin"],
            json={"current_password": "test-password-123", "new_password": "updated-password-123"},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=auth_users["admin"]).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "admin", "password": "test-password-123"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "admin", "password": "updated-password-123"}
        ).status_code
        == 200
    )


def test_seed_twenty_users_idempotent_and_does_not_reset(client):
    with SessionLocal.begin() as db:
        assert seed_users(db) == 20
        users = list(db.scalars(select(User).order_by(User.username)))
        assert len({u.password_hash for u in users}) == 20
        assert all(PASSWORDS.verify("0987654321", u.password_hash) for u in users)
        user = db.scalar(select(User).where(User.username == "user1"))
        user.password_hash = PASSWORDS.hash("changed-password")
        user.role = "viewer"
        user.is_active = False
    with SessionLocal.begin() as db:
        assert seed_users(db) == 0
        assert db.scalar(select(func.count()).select_from(User)) == 20
        user = db.scalar(select(User).where(User.username == "user1"))
        assert PASSWORDS.verify("changed-password", user.password_hash)
        assert user.role == "viewer" and not user.is_active
        assert user.email == "user1@example.com"


def test_missing_secret_fails_closed(client, auth_users, monkeypatch):
    monkeypatch.setattr(get_settings(), "jwt_secret", "")
    assert client.get("/api/v1/auth/me", headers=auth_users["admin"]).status_code == 503


def test_secure_cookie_on_https(client, auth_users, monkeypatch):
    monkeypatch.setattr(get_settings(), "public_url", "https://vena.example.com")
    result = client.post(
        "/api/v1/auth/login", json={"email": "admin", "password": "test-password-123"}
    )
    assert "Secure" in result.headers["set-cookie"]


def test_session_expiry_checked_in_database(client, auth_users):
    with SessionLocal.begin() as db:
        for record in db.scalars(select(AuthSession)):
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me", headers=auth_users["admin"]).status_code == 401
