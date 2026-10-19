from dataclasses import replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, DeliveryLog, Notification, SmvuIngestState
from app.domain import notifications as service
from app.domain.email import build_email_provider
from app.domain.mail_queue import enqueue
from app.domain.predictions import get_prediction_source
from app.domain.settings_store import read_settings
from app.schemas.notifications import NotificationCreate
from app.schemas.predictions import SnapshotStatus

OVERDUE_STATUSES = ("planned", "assigned", "in_progress")
SOURCE_KEY = "data_source_unavailable"


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _exclusive(session: Session, lock: int) -> bool:
    return bool(session.scalar(text("SELECT pg_try_advisory_xact_lock(:lock)"), {"lock": lock}))


def escalate(session: Session, settings: Settings) -> int:
    config = read_settings(session, settings).escalation
    if not config.enabled:
        return 0
    now = _now()
    pending = session.scalars(
        select(Notification)
        .where(
            Notification.severity == "critical",
            Notification.status == "new",
            Notification.escalated_at.is_(None),
            Notification.created_at <= now - timedelta(minutes=config.minutes),
        )
        .order_by(Notification.created_at)
        .limit(50)
        .with_for_update(skip_locked=True)
    ).all()
    if not pending:
        return 0
    demo = get_prediction_source(settings).status().data_source == "demo"
    recipients = service.resolve_recipients(session, settings, config.recipients)
    escalated = 0
    for original in pending:
        original.escalated_at = now
        if demo and original.type == "risk":
            continue
        key = f"escalation:{original.id}"
        notice = f"Не подтверждено за {config.minutes} мин."
        notification = service.create_notification(
            session,
            NotificationCreate(
                type=original.type,  # type: ignore[arg-type]
                severity="critical",
                title=f"Эскалация: {original.title}"[:200],
                description=f"{notice} {original.description}".strip(),
                asset_id=original.asset_id,
                pattern_id=original.pattern_id,
                action_id=original.action_id,
                dedup_key=key,
            ),
        )
        notification.escalated_at = now
        letter = replace(
            service.notification_letter(settings, original),
            kicker="Эскалация",
            summary=f"{notice} {original.description}".strip(),
        )
        if not recipients:
            session.add(
                DeliveryLog(
                    notification_id=notification.id,
                    rule_id="escalation",
                    channel="email",
                    recipient="",
                    dedup_key=key,
                    status="skipped",
                    detail="Не заданы получатели эскалации",
                )
            )
        for recipient in recipients:
            enqueue(
                session,
                recipient,
                f"VENA · {notification.title}",
                letter.text(),
                html=letter.html(),
                notification_id=notification.id,
                rule_id="escalation",
                dedup_key=key,
            )
        escalated += 1
    session.flush()
    return escalated


def notify_overdue_actions(session: Session, settings: Settings) -> int:
    if service.enabled_rule(session, settings, "action_overdue") is None:
        return 0
    if not _exclusive(session, 74918232):
        return 0
    overdue = session.scalars(
        select(Action)
        .where(Action.status.in_(OVERDUE_STATUSES), Action.recommended_at < _now())
        .order_by(Action.recommended_at)
    ).all()
    keys = {
        action.id: f"action_overdue:{action.id}:{action.recommended_at.astimezone(UTC):%Y%m%dT%H%M}"
        for action in overdue
    }
    known = set(
        session.scalars(
            select(Notification.dedup_key).where(Notification.dedup_key.in_(keys.values()))
        )
    )
    created = 0
    for action in overdue:
        if keys[action.id] in known:
            continue
        if service.notify_action(
            session, settings, action, "action_overdue", dedup_key=keys[action.id]
        ):
            created += 1
    return created


def source_outage(
    settings: Settings, status: SnapshotStatus, stream: SmvuIngestState | None
) -> tuple[str, str, str] | None:
    if status.data_source != "journal" or stream is None or stream.received_at is None:
        return None
    now = _now()
    zone = ZoneInfo(settings.timezone)
    silence = (now - stream.received_at).total_seconds()
    if silence > settings.smvu_stale_seconds:
        return (
            f"{SOURCE_KEY}:stream:{stream.received_at.astimezone(UTC):%Y%m%dT%H%M%S}",
            "Поток событий СМВУ не поступает",
            f"Последний пакет принят {stream.received_at.astimezone(zone):%d.%m.%Y %H:%M} "
            f"({int(silence // 60)} мин назад). Прогнозы не пересчитываются по новым событиям.",
        )
    generated = status.generated_at or status.prediction_time
    if (
        generated is not None
        and (now - generated).total_seconds() > settings.prediction_stale_seconds
    ):
        return (
            f"{SOURCE_KEY}:snapshot:{status.snapshot_id}",
            "Снимок прогнозов не обновляется",
            f"Последний снимок рассчитан {generated.astimezone(zone):%d.%m.%Y %H:%M}, "
            "хотя поток СМВУ поступает. Проверьте расчётный контейнер ML.",
        )
    return None


def watch_data_sources(session: Session, settings: Settings) -> Notification | None:
    rule = service.enabled_rule(session, settings, SOURCE_KEY)
    if rule is None:
        return None
    status = get_prediction_source(settings).status()
    outage = source_outage(settings, status, session.get(SmvuIngestState, "default"))
    if outage is None or not _exclusive(session, 74918233):
        return None
    key, title, description = outage
    since = _now() - timedelta(minutes=rule.cooldown_minutes)
    seen = session.scalars(
        select(Notification.id)
        .where(
            Notification.dedup_key.like(f"{SOURCE_KEY}:%"),
            or_(Notification.dedup_key == key, Notification.created_at >= since),
        )
        .limit(1)
    ).first()
    if seen is not None:
        return None
    notification = service.create_notification(
        session,
        NotificationCreate(
            type="system",
            severity=rule.severity,
            title=title,
            description=description,
            dedup_key=key,
        ),
    )
    service.dispatch(session, settings, build_email_provider(settings), notification, SOURCE_KEY)
    return notification
