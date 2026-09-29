import ssl
from unittest.mock import Mock

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core import ldap
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import SessionLocal


def directory_settings(**kwargs):
    return Settings(
        _env_file=None,
        ldap_enabled=True,
        ldap_url="ldaps://directory.example",
        ldap_bind_dn="cn=service,dc=example",
        ldap_bind_password=SecretStr("service-secret"),
        ldap_base_dn="dc=example",
        ldap_group_roles={"cn=dispatchers,dc=example": "dispatcher"},
        **kwargs,
    )


@pytest.mark.parametrize("scheme", ["ldap", "ldaps"])
def test_directory_bind_tls_filter_and_roles(monkeypatch, scheme):
    settings = directory_settings()
    settings.ldap_url = scheme + "://directory.example"
    service = Mock()
    service.result = {"result": 0}
    service.response = [
        {
            "type": "searchResEntry",
            "dn": "cn=user,dc=example",
            "attributes": {
                "sAMAccountName": ["ivan"],
                "objectGUID": [b"stable-id"],
                "mail": ["ivan@example.com"],
                "memberOf": ["CN=Dispatchers,DC=example"],
                "userAccountControl": [512],
            },
        }
    ]
    user = Mock()
    connect = Mock(side_effect=[service, user])
    monkeypatch.setattr(ldap, "_connect", connect)
    tls = Mock(wraps=ldap.Tls)
    monkeypatch.setattr(ldap, "Tls", tls)
    identity = ldap.authenticate(settings, "x*)(uid=*)", "password")
    assert identity.username == "ldap:ivan" and identity.role == "dispatcher"
    assert tls.call_args.kwargs["validate"] == ssl.CERT_REQUIRED
    assert connect.call_args_list[1].args[1:4] == (
        "cn=user,dc=example",
        "password",
        scheme == "ldap",
    )
    assert "x\\2a\\29\\28uid=\\2a\\29" in service.search.call_args.args[1]
    service.unbind.assert_called_once()
    user.unbind.assert_called_once()


def test_directory_refuses_anonymous_bind_and_tls_downgrade(monkeypatch):
    with pytest.raises(ldap.DirectoryDenied):
        ldap.authenticate(directory_settings(), "ivan", "")
    connection = Mock(closed=False)
    connection.start_tls.return_value = False
    monkeypatch.setattr(ldap, "Connection", Mock(return_value=connection))
    with pytest.raises(ldap.DirectoryUnavailable):
        ldap._connect(Mock(), "dn", "password", True, 5)
    connection.bind.assert_not_called()
    connection.unbind.assert_called_once()


def test_directory_disabled_group_and_ambiguous_identity(monkeypatch):
    settings = directory_settings(ldap_default_role="none")
    service = Mock(result={"result": 0})
    entry = {"type": "searchResEntry", "dn": "cn=u", "attributes": {"userAccountControl": [2]}}
    monkeypatch.setattr(ldap, "_connect", Mock(return_value=service))
    for response in [[], [entry, entry], [entry]]:
        service.response = response
        with pytest.raises(ldap.DirectoryDenied):
            ldap.authenticate(settings, "u", "password")
    entry["attributes"] = {"sAMAccountName": ["u"], "mail": ["u@example.com"], "objectGUID": ["id"]}
    service.response = [entry]
    with pytest.raises(ldap.DirectoryDenied):
        ldap.authenticate(settings, "u", "password")


def test_ldap_jwt_and_no_local_password_fallback(client, auth_users, monkeypatch):
    identity = ldap.DirectoryIdentity("a" * 64, "ldap:ivan", "ivan@example.com", "dispatcher")
    monkeypatch.setattr(ldap, "authenticate", lambda *args: identity)
    response = client.post(
        "/api/v1/auth/ldap", json={"login": "ivan", "password": "directory-secret"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["auth_method"] == "ldap"
    token = {"Authorization": "Bearer " + response.json()["access_token"]}
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers=token).json()["auth_method"] == "ldap"
    assert (
        client.post(
            "/api/v1/auth/login", json={"login": "ivan@example.com", "password": "directory-secret"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/password",
            headers=token,
            json={"current_password": "directory-secret", "new_password": "new-password-123"},
        ).status_code
        == 400
    )
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.directory_id == identity.directory_id))
        assert user.password_hash == "!ldap"
        user_id = user.id
    assert (
        client.patch(
            f"/api/v1/users/{user_id}", headers=auth_users["admin"], json={"role": "admin"}
        ).status_code
        == 400
    )
    assert (
        client.patch(
            f"/api/v1/users/{user_id}", headers=auth_users["admin"], json={"is_active": False}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=token).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/ldap", json={"login": "ivan", "password": "directory-secret"}
        ).status_code
        == 401
    )


def test_ldap_collision_does_not_link_local_admin_and_limits_failures(
    client, auth_users, monkeypatch
):
    monkeypatch.setattr(
        ldap,
        "authenticate",
        lambda *args: ldap.DirectoryIdentity("b" * 64, "ldap:admin", "admin@example.com", "admin"),
    )
    assert (
        client.post(
            "/api/v1/auth/ldap", json={"login": "admin", "password": "directory-secret"}
        ).status_code
        == 409
    )
    monkeypatch.setattr(get_settings(), "auth_login_limit", 2)

    def deny(*args):
        raise ldap.DirectoryDenied()

    monkeypatch.setattr(ldap, "authenticate", deny)
    assert [
        client.post("/api/v1/auth/ldap", json={"login": "invalid", "password": "wrong"}).status_code
        for _ in range(3)
    ] == [401, 401, 429]


def test_admin_users_lifecycle_and_rbac(client, auth_users):
    body = {
        "username": "new-user",
        "email": "new@example.com",
        "password": "new-password-123",
        "role": "viewer",
    }
    assert (
        client.post("/api/v1/users", headers=auth_users["dispatcher"], json=body).status_code == 403
    )
    response = client.post("/api/v1/users", headers=auth_users["admin"], json=body)
    assert response.status_code == 201, response.text
    user = response.json()
    assert "password" not in response.text
    assert client.post("/api/v1/users", headers=auth_users["admin"], json=body).status_code == 409
    login = client.post(
        "/api/v1/auth/login", json={"login": "new-user", "password": body["password"]}
    ).json()
    client.cookies.clear()
    token = {"Authorization": "Bearer " + login["access_token"]}
    assert (
        client.patch(
            f"/api/v1/users/{user['id']}", headers=auth_users["admin"], json={"role": "dispatcher"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/auth/me", headers=token).status_code == 401
    assert (
        client.post(
            f"/api/v1/users/{user['id']}/password",
            headers=auth_users["admin"],
            json={"password": "reset-password-123"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"login": "new-user", "password": body["password"]}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"login": "new-user", "password": "reset-password-123"}
        ).status_code
        == 200
    )
    client.cookies.clear()
    users = client.get("/api/v1/users", headers=auth_users["admin"]).json()["items"]
    admin_id = next(row["id"] for row in users if row["username"] == "admin")
    assert (
        client.patch(
            f"/api/v1/users/{admin_id}", headers=auth_users["admin"], json={"is_active": False}
        ).status_code
        == 409
    )
