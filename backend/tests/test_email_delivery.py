from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.db.models import DeliveryLog, Notification, utcnow
from app.db.session import SessionLocal
from app.domain.email import build_email_provider
from app.domain.mail_queue import deliver_pending
from app.domain.notifications import create_notification, dispatch
from app.schemas.notifications import NotificationCreate


def configure(client):
    assert (
        client.put(
            "/api/v1/settings/notifications",
            json={
                "recipients": [
                    {"id": "dispatcher_team", "name": "Диспетчеры", "emails": ["duty@example.com"]},
                    {
                        "id": "maintenance_team",
                        "name": "Эксплуатация",
                        "emails": ["duty@example.com"],
                    },
                ]
            },
        ).status_code
        == 200
    )


class FakeSMTP:
    configured = True

    def __init__(self, fails=0):
        self.fails, self.messages = fails, []

    def send(self, recipient, subject, body, *, delivery_id=None):
        self.messages.append((recipient, subject, body, delivery_id))
        if len(self.messages) <= self.fails:
            raise OSError("sensitive server text")


def test_transactional_delivery_and_retry(client):
    configure(client)
    assert (
        client.post(
            "/api/v1/notifications",
            json={
                "type": "risk",
                "severity": "critical",
                "title": "Критический риск",
                "description": "Растёт риск отказа насоса",
                "asset_id": "42",
            },
        ).status_code
        == 201
    )
    fake = FakeSMTP(fails=1)
    with SessionLocal() as db:
        log = db.scalars(select(DeliveryLog).where(DeliveryLog.channel == "email")).one()
        assert log.status == "pending" and log.attempts == 0
        assert deliver_pending(db, fake) == 0
        db.refresh(log)
        assert log.status == "pending" and log.attempts == 1
        assert "sensitive" not in log.detail
        assert deliver_pending(db, fake) == 0
        log.next_attempt_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert deliver_pending(db, fake) == 1
        db.refresh(log)
        assert log.status == "sent" and log.sent_at and log.attempts == 2
        assert deliver_pending(db, fake) == 0
    assert fake.messages[0] == fake.messages[1]
    assert "Критический" in fake.messages[1][2]


def test_failed_mail_stops_after_six_attempts(client):
    configure(client)
    client.post(
        "/api/v1/notifications", json={"type": "system", "severity": "info", "title": "Событие"}
    )
    fake = FakeSMTP(fails=9)
    with SessionLocal() as db:
        log = db.scalars(select(DeliveryLog).where(DeliveryLog.channel == "email")).one()
        for _ in range(6):
            log.next_attempt_at = utcnow() - timedelta(seconds=1)
            db.commit()
            deliver_pending(db, fake)
        db.refresh(log)
        assert log.status == "failed" and log.attempts == 6
        assert deliver_pending(db, fake) == 0


def test_rollback_and_recipient_deduplication(client):
    configure(client)
    fake = FakeSMTP()
    with SessionLocal() as db:
        notification = create_notification(
            db, NotificationCreate(type="integration", severity="attention", title="Неисправность")
        )
        dispatch(db, get_settings(), fake, notification, "alarm_event")
        assert (
            db.scalar(
                select(func.count()).select_from(DeliveryLog).where(DeliveryLog.channel == "email")
            )
            == 1
        )
        assert not fake.messages
        db.rollback()
        assert deliver_pending(db, fake) == 0
        assert db.scalar(select(func.count()).select_from(Notification)) == 0


def test_event_batches_notify_only_new_events(client, monkeypatch, tmp_path):
    configure(client)
    monkeypatch.setattr(get_settings(), "inbox_dir", tmp_path)
    event = {
        "event_id": "mail-1",
        "channel_id": "42",
        "ts": "2026-09-29T12:00:00+03:00",
        "alarm": True,
        "value": "Неисправен",
    }
    body = {"batch_id": "mail-batch", "event_count": 1, "events": [event]}
    assert client.post("/api/v1/smvu/events", json=body).status_code == 202
    assert client.post("/api/v1/smvu/events", json=body).json()["last_event_count"] == 0
    with SessionLocal() as db:
        assert db.scalars(select(Notification)).one().severity == "attention"
        log = db.scalars(select(DeliveryLog).where(DeliveryLog.channel == "email")).one()
        assert log.rule_id == "alarm_event" and "Тревожных: 1" in log.body


def test_disabled_groups_and_explicit_empty_settings(client):
    client.put(
        "/api/v1/settings/notifications",
        json={
            "recipients": [
                {
                    "id": "dispatcher_team",
                    "name": "Диспетчеры",
                    "emails": ["duty@example.com"],
                    "enabled": False,
                },
            ]
        },
    )
    client.post(
        "/api/v1/notifications", json={"type": "system", "severity": "info", "title": "Событие"}
    )
    with SessionLocal() as db:
        log = db.scalars(select(DeliveryLog).where(DeliveryLog.channel == "email")).one()
        assert log.status == "skipped" and not log.recipient
    assert (
        client.put(
            "/api/v1/settings/notifications", json={"recipients": [], "rules": []}
        ).status_code
        == 200
    )
    config = client.get("/api/v1/settings/notifications").json()
    assert config["recipients"] == [] and config["rules"] == []


@pytest.mark.parametrize("secure", [False, True])
def test_smtp_aliases_tls_and_idempotency(monkeypatch, secure):
    settings = Settings(
        SMTP_HOST="smtp.resend.com",
        SMTP_PORT=465 if secure else 587,
        SMTP_USER="resend",
        SMTP_PASSWORD="test-secret",
        SMTP_SECURE=secure,
        SMTP_FROM="Vena <no-reply@example.com>",
    )
    smtp = MagicMock()
    monkeypatch.setattr("app.domain.email.smtplib.SMTP", smtp)
    monkeypatch.setattr("app.domain.email.smtplib.SMTP_SSL", smtp)
    build_email_provider(settings).send("duty@example.com", "Проверка", "Событие", delivery_id="42")
    client = smtp.return_value.__enter__.return_value
    assert client.starttls.call_count == (0 if secure else 1)
    if not secure:
        assert client.starttls.call_args.kwargs["context"].check_hostname
    else:
        assert smtp.call_args.kwargs["context"].check_hostname
    client.login.assert_called_once_with("resend", "test-secret")
    message = client.send_message.call_args.args[0]
    assert message["Resend-Idempotency-Key"] == "vena-delivery/42"
    assert message["From"] == "Vena <no-reply@example.com>"
    assert "test-secret" not in repr(settings)


def test_mail_admin_permissions(client, auth_users):
    for role in ["viewer", "dispatcher"]:
        assert (
            client.post(
                "/api/v1/notifications/test",
                headers=auth_users[role],
                json={"recipient": "duty@example.com"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/v1/integrations/email/deliveries", headers=auth_users[role]
            ).status_code
            == 403
        )
    assert (
        client.get("/api/v1/integrations/email/deliveries", headers=auth_users["admin"]).status_code
        == 200
    )


def test_actual_smtp_transport_to_local_capture_server(client):
    import socketserver
    import threading
    from email import policy
    from email.parser import BytesParser

    messages = []

    class Handler(socketserver.StreamRequestHandler):
        def handle(self):
            self.wfile.write(b"220 local-test ESMTP\r\n")
            while line := self.rfile.readline():
                command = line.split(b" ", 1)[0].strip().upper()
                if command == b"DATA":
                    self.wfile.write(b"354 Send message\r\n")
                    data = b""
                    while (part := self.rfile.readline()) != b".\r\n":
                        if not part:
                            return
                        data += part
                    messages.append(BytesParser(policy=policy.default).parsebytes(data))
                if command == b"QUIT":
                    self.wfile.write(b"221 Bye\r\n")
                    return
                self.wfile.write(b"250 OK\r\n")

    configure(client)
    client.post(
        "/api/v1/notifications",
        json={
            "type": "risk",
            "severity": "critical",
            "title": "Проверка SMTP",
            "description": "Проверка доставки в изолированный почтовый сервер",
        },
    )
    with socketserver.TCPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = build_email_provider(
                Settings(
                    SMTP_HOST="127.0.0.1",
                    SMTP_PORT=server.server_address[1],
                    SMTP_TLS=False,
                    SMTP_FROM="Vena <no-reply@example.com>",
                )
            )
            with SessionLocal() as db:
                assert deliver_pending(db, provider) == 1
        finally:
            server.shutdown()
            thread.join()
    assert len(messages) == 1
    assert messages[0]["To"] == "duty@example.com"
    assert messages[0]["Subject"] == "VENA · Проверка SMTP"
    assert "Критический" in messages[0].get_content()


def test_demonstration_forecasts_cannot_send_mail(client):
    configure(client)
    with SessionLocal() as db:
        notification = create_notification(
            db,
            NotificationCreate(type="risk", severity="critical", title="Демонстрационный прогноз"),
        )
        dispatch(db, get_settings(), FakeSMTP(), notification, "critical_risk", allow_email=False)
        assert (
            db.scalar(
                select(func.count()).select_from(DeliveryLog).where(DeliveryLog.channel == "email")
            )
            == 0
        )
