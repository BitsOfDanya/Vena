from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Action, ActionEvent, Notification
from app.domain.spatial import ensure_demo_spatial


def _now() -> datetime:
    return datetime.now(tz=UTC)


def seed_demo(session: Session) -> bool:
    ensure_demo_spatial(session)
    if session.scalars(select(Action.id).limit(1)).first() is not None:
        return False
    now = _now()

    notifications = [
        Notification(
            id="N-2051",
            type="risk",
            severity="critical",
            title="P-0142 · risk 68/100",
            description="Рост нетипичных переходов и повторные отказы за последние сутки.",
            asset_id="P-0142",
            created_at=now - timedelta(minutes=45),
            status="new",
        ),
        Notification(
            id="N-2050",
            type="pattern",
            severity="attention",
            title="Pattern 001 · 4 systems",
            description=(
                "Связанная активность в системах водоотведения, вентиляции, дыма и питания."
            ),
            pattern_id="pattern-001",
            created_at=now - timedelta(hours=2),
            status="new",
        ),
        Notification(
            id="N-2049",
            type="risk",
            severity="attention",
            title="PH-0871 · risk 58/100",
            description="Повторяющиеся изменения состояния питания на канале.",
            asset_id="PH-0871",
            created_at=now - timedelta(hours=5),
            status="acknowledged",
            read_at=now - timedelta(hours=4),
            acknowledged_at=now - timedelta(hours=4),
        ),
    ]
    session.add_all(notifications)

    actions = [
        Action(
            id="A-1001",
            asset_id="P-0142",
            source="vena_forecast",
            source_detail="Pump72",
            kind="inspect",
            reason="Высокая повторяемость, рост числа переходов",
            priority="high",
            window_start=now,
            recommended_at=now + timedelta(hours=24),
            status="assigned",
            assignee="Бригада А",
            notify_channels="in_app",
            created_by="Duty engineer",
            created_at=now - timedelta(hours=2),
            updated_at=now - timedelta(hours=1),
        ),
        Action(
            id="A-1002",
            asset_id="PH-0871",
            source="vena_forecast",
            source_detail="Power24",
            kind="electrical diagnostic",
            reason="Повторяющиеся изменения состояния питания",
            priority="medium",
            window_start=now + timedelta(hours=8),
            recommended_at=now + timedelta(hours=32),
            status="planned",
            assignee="Электротехническая бригада",
            created_by="Duty engineer",
            created_at=now - timedelta(hours=5),
            updated_at=now - timedelta(hours=5),
        ),
        Action(
            id="A-1003",
            asset_id="F-0312",
            source="vena_forecast",
            source_detail="Fan72",
            kind="service",
            reason="Частота событий выше базовой по каналу",
            priority="medium",
            window_start=now + timedelta(hours=26),
            recommended_at=now + timedelta(hours=60),
            status="suggested",
            assignee="Бригада Б",
            created_by="VENA",
            created_at=now - timedelta(minutes=40),
            updated_at=now - timedelta(minutes=40),
        ),
        Action(
            id="A-1004",
            asset_id="S-4412",
            source="vena_forecast",
            source_detail="Alarm corroboration",
            kind="verify",
            reason="Единичная серия тревог, нужна проверка на месте",
            priority="low",
            window_start=now + timedelta(hours=48),
            recommended_at=now + timedelta(hours=70),
            status="suggested",
            assignee="Дежурный инженер",
            created_by="VENA",
            created_at=now - timedelta(minutes=90),
            updated_at=now - timedelta(minutes=90),
        ),
        Action(
            id="A-0997",
            asset_id="P-0142",
            source="vena_forecast",
            source_detail="Pump72",
            kind="service",
            reason="Отказ после окна эскалации",
            priority="high",
            window_start=now - timedelta(hours=96),
            recommended_at=now - timedelta(hours=90),
            status="completed",
            assignee="Бригада А",
            created_by="Duty engineer",
            created_at=now - timedelta(hours=100),
            updated_at=now - timedelta(hours=91),
            result_outcome="maintenance_performed",
            result_note="Заменён контактор",
            completed_at=now - timedelta(hours=91),
        ),
    ]
    session.add_all(actions)
    session.flush()

    history = [
        ("A-1001", "suggested", "VENA", now - timedelta(hours=3), None, None),
        ("A-1001", "approved", "Duty engineer", now - timedelta(hours=2), "suggested", "planned"),
        (
            "A-1001",
            "assigned",
            "Duty engineer",
            now - timedelta(minutes=100),
            "planned",
            "assigned",
        ),
        ("A-1002", "suggested", "VENA", now - timedelta(hours=6), None, None),
        ("A-1002", "approved", "Duty engineer", now - timedelta(hours=5), "suggested", "planned"),
        ("A-1003", "suggested", "VENA", now - timedelta(minutes=40), None, None),
        ("A-1004", "suggested", "VENA", now - timedelta(minutes=90), None, None),
        ("A-0997", "completed", "Бригада А", now - timedelta(hours=91), "in_progress", "completed"),
        ("A-0997", "result_recorded", "Бригада А", now - timedelta(hours=91), None, None),
    ]
    for action_id, event_type, actor, at, from_status, to_status in history:
        session.add(
            ActionEvent(
                action_id=action_id,
                event_type=event_type,
                actor=actor,
                at=at,
                from_status=from_status,
                to_status=to_status,
                note="",
            )
        )
    session.flush()
    return True
