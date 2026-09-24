from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog, ImportBatch, TelemetryEvent
from app.db.session import SessionLocal
from app.domain.imports import process_batch


def test_registration_roles_and_session(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/v1/auth/me").json()["role"] == "dispatcher"
    audit = client.get("/api/v1/audit")
    assert audit.status_code == 200
    assert any(row["path"] == "/api/v1/auth/register" for row in audit.json())
    client.post("/api/v1/auth/logout")
    with SessionLocal() as session:
        logout = session.scalar(select(AuditLog).where(AuditLog.path == "/api/v1/auth/logout"))
        assert logout is not None and logout.status_code == 204
    assert client.get("/api/v1/data/summary").status_code == 401
    blocked = client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "full_name": "Второй диспетчер",
            "password": "test-password-123",
            "role": "dispatcher",
        },
    )
    assert blocked.status_code == 403
    monkeypatch.setattr(get_settings(), "dispatcher_invite_code", "")
    assert client.post(
        "/api/v1/auth/register",
        json={
            "email": "second@example.com",
            "full_name": "Второй диспетчер",
            "password": "test-password-123",
            "role": "dispatcher",
        },
    ).status_code == 201
    registered = client.post(
        "/api/v1/auth/register",
        json={
            "email": "operator@example.com",
            "full_name": "Тестовый оператор",
            "password": "test-password-123",
            "role": "operator",
        },
    )
    assert registered.status_code == 201
    assert client.post("/api/v1/actions", json={}).status_code == 403
    assert client.get("/api/v1/actions").status_code == 403
    assert client.get("/api/v1/audit").status_code == 403


def test_operator_uploads_events_and_worker_imports(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "operator@example.com",
            "full_name": "Тестовый оператор",
            "password": "test-password-123",
            "role": "operator",
        },
    )
    body = (
        "ИД записи журнала;ИД канала данных;ИД типа канала данных;Текущее значение;Дата записи\n"
        "3008235019;56682;12;25,00;19.10.2026 12:15\n"
    ).encode()
    uploaded = client.post(
        "/api/v1/imports?kind=events",
        files={"file": ("events.csv", BytesIO(body), "text/csv")},
    )
    assert uploaded.status_code == 201, uploaded.text
    batch_id = uploaded.json()["id"]
    with SessionLocal() as session:
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None
        process_batch(session, batch)
        event = session.scalar(select(TelemetryEvent))
        assert event is not None
        assert event.value_numeric == 25.0
    assert client.get(f"/api/v1/imports/{batch_id}").json()["status"] == "completed"
    assert client.get("/api/v1/data/summary").json()["events"] == 1
