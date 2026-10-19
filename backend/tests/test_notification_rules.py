import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import DeliveryLog, Notification, SettingsRecord, SmvuIngestState, utcnow
from app.db.session import SessionLocal
from app.domain import scheduler
from app.domain.digest import send_digest
from app.domain.email import Letter, build_email_provider
from app.domain.predictions import reset_prediction_source
from app.domain.watchdog import escalate, notify_overdue_actions, watch_data_sources
from tests.test_predictions import row, write_snapshot

CATALOGUE = get_settings().ml_dir / "configs" / "recommendations.json"


@pytest.fixture()
def ml_root(tmp_path: Path):
    settings = get_settings()
    original = settings.ml_dir
    settings.ml_dir = tmp_path
    reset_prediction_source()
    yield tmp_path
    settings.ml_dir = original
    reset_prediction_source()


def journal_snapshot(root: Path, generated: datetime, rows: list[dict], source="journal") -> None:
    write_snapshot(root, generated, rows)
    path = root / "results" / "predictions" / "snapshot.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**payload, "data_source": source}), encoding="utf-8")
    reset_prediction_source()


def configure(client: TestClient, **extra) -> None:
    groups = [
        {"id": "dispatcher_team", "name": "Диспетчеры", "emails": ["duty@example.com"]},
        {"id": "maintenance_team", "name": "Эксплуатация", "emails": ["crew@example.com"]},
        {"id": "management", "name": "Руководство", "emails": ["boss@example.com"]},
    ]
    response = client.put("/api/v1/settings/notifications", json={"recipients": groups, **extra})
    assert response.status_code == 200


def enable_rule(client: TestClient, rule_id: str) -> None:
    rules = client.get("/api/v1/settings/notifications").json()["rules"]
    for rule in rules:
        rule["enabled"] = rule["enabled"] or rule["id"] == rule_id
    assert client.put("/api/v1/settings/notifications", json={"rules": rules}).status_code == 200


def action(client: TestClient, due: datetime, **extra) -> str:
    payload = {
        "asset_id": "P-0142",
        "reason": "Рост частоты событий",
        "recommended_at": due.isoformat(),
        "assignee": "Бригада А",
        **extra,
    }
    response = client.post("/api/v1/actions", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


def mails(notification_id: str) -> list[DeliveryLog]:
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(DeliveryLog).where(
                    DeliveryLog.notification_id == notification_id, DeliveryLog.channel == "email"
                )
            )
        )


def test_critical_forecast_mail_explains_incident(client: TestClient, ml_root: Path) -> None:
    (ml_root / "configs").mkdir(parents=True, exist_ok=True)
    shutil.copy(CATALOGUE, ml_root / "configs" / "recommendations.json")
    journal_snapshot(ml_root, datetime.now(tz=UTC), [row("100", 0.995, "critical")])
    configure(client)

    assert client.post("/api/v1/predictions/refresh").json()["notifications_created"] == 1

    notification = client.get("/api/v1/notifications").json()[0]
    [mail] = mails(notification["id"])
    assert mail.recipient == "duty@example.com"
    for line in [
        "Уровень: Критично",
        "Оценка модели: 0.995 за 72 ч",
        "Горизонт: 72 ч",
        "Канал: 100",
        "Сценарий: Подтопление",
        "Причина: ",
        "Первый шаг: ",
        "Если не отреагировать: ",
    ]:
        assert line in mail.body
    assert mail.html and mail.html.startswith("<!doctype html>")
    assert "Если не отреагировать" in mail.html and "#22695f" in mail.html
    link = f"{get_settings().public_url}/pulse?notification={notification['id']}"
    assert f'href="{link}"' in mail.html and link in mail.body


def test_mail_escapes_dynamic_values(client: TestClient, ml_root: Path) -> None:
    configure(client)
    response = client.post(
        "/api/v1/notifications",
        json={
            "type": "risk",
            "severity": "critical",
            "title": "<script>alert(1)</script>",
            "description": 'Канал "A" & <b>B</b>',
            "asset_id": "<img>",
        },
    )

    [mail] = mails(response.json()["id"])
    assert "<script>" not in mail.html and "&lt;script&gt;alert(1)&lt;/script&gt;" in mail.html
    assert "Канал &quot;A&quot; &amp; &lt;b&gt;B&lt;/b&gt;" in mail.html
    assert "<img>" not in mail.html
    assert 'Канал "A" & <b>B</b>' in mail.body and "Уровень: Критично" in mail.body


def test_letter_text_and_html_carry_the_same_content() -> None:
    letter = Letter(
        kicker="Утренняя сводка",
        title="Сводка",
        link="https://vena.example/pulse?a=1&b=2",
        facts=[("Уровень", "Внимание")],
        notes=[("Первый шаг", "Проверить насос")],
        sections=[("Просрочено", ["A-1 · P-1"]), ("Завершено", [])],
    )

    text, html = letter.text(), letter.html()
    for value in ["Уровень", "Внимание", "Проверить насос", "A-1 · P-1", "Просрочено"]:
        assert value in text and value in html
    assert 'href="https://vena.example/pulse?a=1&amp;b=2"' in html
    assert "Открыть в VENA: https://vena.example/pulse?a=1&b=2" in text
    assert "max-width:600px" in html and "VENA" in html


def test_digest_mail_has_html_part(client: TestClient, ml_root: Path, monkeypatch) -> None:
    configure(client)
    monkeypatch.setattr(get_settings(), "digest_enabled", True)
    with SessionLocal() as db:
        assert send_digest(db, get_settings(), build_email_provider(get_settings())) == 2
        db.commit()
        log = db.scalars(select(DeliveryLog).where(DeliveryLog.rule_id == "morning_brief")).first()
    assert log is not None and "Работы к сроку" in log.body and "Работы к сроку" in log.html


def test_unacknowledged_critical_escalates_once(client: TestClient, ml_root: Path) -> None:
    configure(client)
    defaults = client.get("/api/v1/settings/notifications").json()["escalation"]
    assert defaults == {"enabled": True, "minutes": 30, "recipients": ["management"]}
    critical = {"type": "risk", "severity": "critical", "title": "Подтопление", "asset_id": "7"}
    pending = client.post("/api/v1/notifications", json=critical).json()["id"]
    handled = client.post("/api/v1/notifications", json=critical).json()["id"]
    client.patch(f"/api/v1/notifications/{handled}", json={"status": "acknowledged"})
    client.post("/api/v1/notifications", json={**critical, "severity": "attention"})
    settings = get_settings()

    with SessionLocal() as db:
        assert escalate(db, settings) == 0
        for item in db.scalars(select(Notification)):
            item.created_at = utcnow() - timedelta(minutes=31)
        db.commit()
        assert escalate(db, settings) == 1
        db.commit()
        for item in db.scalars(select(Notification)):
            item.created_at = utcnow() - timedelta(hours=2)
        db.commit()
        assert escalate(db, settings) == 0
        db.commit()
        escalations = db.scalars(
            select(Notification).where(Notification.dedup_key == f"escalation:{pending}")
        ).all()
        sent = db.scalars(select(DeliveryLog).where(DeliveryLog.rule_id == "escalation")).all()

    assert [item.title for item in escalations] == ["Эскалация: Подтопление"]
    assert escalations[0].severity == "critical" and escalations[0].status == "new"
    assert [item.recipient for item in sent] == ["boss@example.com"]
    assert sent[0].subject == "VENA · Эскалация: Подтопление"
    assert "Не подтверждено за 30 мин." in sent[0].body and sent[0].html


def test_escalation_settings_are_validated_and_backward_compatible(client: TestClient) -> None:
    with SessionLocal() as db:
        db.add(SettingsRecord(key="notifications", value=json.dumps({"recipients": []})))
        db.commit()
    assert client.get("/api/v1/settings/notifications").json()["escalation"]["minutes"] == 30

    rejected = client.put("/api/v1/settings/notifications", json={"escalation": {"minutes": 0}})
    updated = client.put(
        "/api/v1/settings/notifications", json={"escalation": {"minutes": 10, "enabled": False}}
    )
    unchanged = client.put("/api/v1/settings/notifications", json={"recipients": []})

    assert rejected.status_code == 422
    assert updated.json()["escalation"]["minutes"] == 10
    assert unchanged.json()["escalation"] == {
        "enabled": False,
        "minutes": 10,
        "recipients": ["management"],
    }
    with SessionLocal() as db:
        assert escalate(db, get_settings()) == 0


def test_demo_forecasts_are_not_escalated(client: TestClient, ml_root: Path) -> None:
    journal_snapshot(ml_root, datetime.now(tz=UTC), [], source="demo")
    configure(client)
    client.post(
        "/api/v1/notifications", json={"type": "risk", "severity": "critical", "title": "Демо"}
    )
    with SessionLocal() as db:
        for item in db.scalars(select(Notification)):
            item.created_at = utcnow() - timedelta(hours=1)
        db.commit()
        assert escalate(db, get_settings()) == 0
        db.commit()
        assert all(item.escalated_at for item in db.scalars(select(Notification)))


def test_assignment_notifies_with_requested_channels(client: TestClient) -> None:
    configure(client)
    soon = datetime.now(tz=UTC) + timedelta(hours=4)
    quiet = action(client, soon)
    plain = action(client, soon)
    loud = action(client, soon)
    assert client.get("/api/v1/notifications", params={"type": "action"}).json() == []

    client.post(f"/api/v1/actions/{plain}/assign", json={"assignee": "Бригада Б"})
    client.post(f"/api/v1/actions/{loud}/assign", json={"assignee": "Бригада В", "notify": True})
    client.patch(f"/api/v1/actions/{quiet}", json={"assignee": "Бригада А"})
    client.patch(f"/api/v1/actions/{quiet}", json={"assignee": "Бригада Г"})
    emailed = action(client, soon, notify_channels=["in_app", "email"])
    in_app = action(client, soon, notify_channels=["in_app"])

    listed = client.get("/api/v1/notifications", params={"type": "action"}).json()
    by_action = {item["action_id"]: item for item in listed}
    assert set(by_action) == {plain, loud, quiet, emailed, in_app}
    assert by_action[loud]["title"] == f"Назначена работа {loud} · P-0142"
    assert by_action[loud]["severity"] == "info"
    assert "Бригада В" in by_action[loud]["description"]
    assert mails(by_action[plain]["id"]) == [] and mails(by_action[in_app]["id"]) == []
    assert mails(by_action[quiet]["id"]) == []
    [mail] = mails(by_action[loud]["id"])
    assert mail.recipient == "crew@example.com" and "Исполнитель: Бригада В" in mail.body
    assert f"/actions?action={loud}" in mail.html
    assert [item.recipient for item in mails(by_action[emailed]["id"])] == ["crew@example.com"]


def test_assignment_rule_can_be_disabled(client: TestClient) -> None:
    rules = client.get("/api/v1/settings/notifications").json()["rules"]
    for rule in rules:
        rule["enabled"] = rule["id"] != "action_assigned"
    client.put("/api/v1/settings/notifications", json={"rules": rules})
    action_id = action(client, datetime.now(tz=UTC) + timedelta(hours=4))

    client.post(f"/api/v1/actions/{action_id}/assign", json={"assignee": "Бригада Б"})

    assert client.get("/api/v1/notifications", params={"type": "action"}).json() == []


def test_overdue_actions_notify_once_per_due_date(client: TestClient) -> None:
    configure(client)
    now = datetime.now(tz=UTC)
    late = action(client, now - timedelta(hours=2))
    action(client, now + timedelta(hours=2))
    action(client, now - timedelta(hours=2), status="suggested")
    settings = get_settings()
    with SessionLocal() as db:
        assert notify_overdue_actions(db, settings) == 0
    enable_rule(client, "action_overdue")

    with SessionLocal() as db:
        assert notify_overdue_actions(db, settings) == 1
        db.commit()
        assert notify_overdue_actions(db, settings) == 0
        db.commit()
    moved = (now - timedelta(minutes=5)).isoformat()
    client.patch(f"/api/v1/actions/{late}", json={"recommended_at": moved})
    with SessionLocal() as db:
        assert notify_overdue_actions(db, settings) == 1
        db.commit()

    listed = client.get("/api/v1/notifications", params={"type": "action"}).json()
    assert [item["title"] for item in listed] == [f"Работа просрочена: {late} · P-0142"] * 2
    assert listed[0]["severity"] == "attention"
    sent = mails(listed[-1]["id"])
    assert sorted(item.recipient for item in sent) == ["boss@example.com", "crew@example.com"]
    assert sent[0].rule_id == "action_overdue" and "VENA · Работа просрочена" in sent[0].body


def test_stale_stream_raises_one_source_notification(client: TestClient, ml_root: Path) -> None:
    configure(client)
    journal_snapshot(ml_root, datetime.now(tz=UTC), [])
    settings = get_settings()
    with SessionLocal() as db:
        assert watch_data_sources(db, settings) is None
        db.add(SmvuIngestState(id="default", received_at=utcnow() - timedelta(minutes=20)))
        db.commit()
        first = watch_data_sources(db, settings)
        db.commit()
        assert watch_data_sources(db, settings) is None
        state = db.get(SmvuIngestState, "default")
        assert state is not None
        state.received_at = utcnow() - timedelta(minutes=16)
        db.commit()
        assert watch_data_sources(db, settings) is None

    assert first is not None and first.title == "Поток событий СМВУ не поступает"
    assert first.severity == "critical" and first.type == "system"
    sent = mails(first.id)
    assert sorted(item.recipient for item in sent) == ["boss@example.com", "duty@example.com"]
    assert "/settings/integrations" in sent[0].html


def test_stale_snapshot_with_live_stream_is_an_outage(client: TestClient, ml_root: Path) -> None:
    journal_snapshot(ml_root, datetime.now(tz=UTC) - timedelta(days=2), [])
    with SessionLocal() as db:
        db.add(SmvuIngestState(id="default", received_at=utcnow()))
        db.commit()
        notification = watch_data_sources(db, get_settings())
        db.commit()
    assert notification is not None and notification.title == "Снимок прогнозов не обновляется"


@pytest.mark.parametrize("source", ["journal", "demo"])
def test_historical_or_demo_source_is_not_an_outage(
    client: TestClient, ml_root: Path, source: str
) -> None:
    journal_snapshot(ml_root, datetime.now(tz=UTC) - timedelta(days=90), [], source=source)
    with SessionLocal() as db:
        if source == "demo":
            db.add(SmvuIngestState(id="default", received_at=utcnow() - timedelta(hours=3)))
            db.commit()
        assert watch_data_sources(db, get_settings()) is None


def test_digest_time_change_reschedules_job(client: TestClient) -> None:
    assert scheduler._scheduler is not None
    response = client.put(
        "/api/v1/settings/notifications",
        json={"digest": {"hour": 6, "minute": 45, "timezone": "Asia/Yekaterinburg"}},
    )
    invalid = client.put(
        "/api/v1/settings/notifications", json={"digest": {"timezone": "Mars/Olympus"}}
    )

    assert response.status_code == 200 and invalid.status_code == 422
    job = scheduler._scheduler.get_job("morning_brief")
    assert "hour='6'" in str(job.trigger) and "minute='45'" in str(job.trigger)
    assert str(job.trigger.timezone) == "Asia/Yekaterinburg"
    assert client.get("/api/v1/settings/notifications").json()["digest"]["hour"] == 6
