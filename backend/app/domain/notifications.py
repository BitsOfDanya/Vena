from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import DeliveryLog, Notification
from app.domain.email import EmailProvider, alert_body
from app.domain.settings_store import read_settings
from app.schemas.notifications import NotificationCreate, NotificationPatch

ALLOWED_TRANSITIONS = {
    "new": {"acknowledged", "resolved"},
    "acknowledged": {"resolved"},
    "resolved": set[str](),
}


class InvalidTransition(Exception):
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:10]}"


def list_notifications(
    session: Session,
    status: str | None = None,
    severity: str | None = None,
    type_: str | None = None,
    asset_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Notification]:
    statement = select(Notification).order_by(Notification.created_at.desc())
    if status:
        statement = statement.where(Notification.status == status)
    if severity:
        statement = statement.where(Notification.severity == severity)
    if type_:
        statement = statement.where(Notification.type == type_)
    if asset_id:
        statement = statement.where(Notification.asset_id == asset_id)
    return list(session.scalars(statement.offset(offset).limit(limit)))


def get_notification(session: Session, notification_id: str) -> Notification | None:
    return session.get(Notification, notification_id)


def patch_notification(
    session: Session, notification: Notification, patch: NotificationPatch
) -> Notification:
    now = _now()
    if patch.read and notification.read_at is None:
        notification.read_at = now
    if patch.status is not None:
        if patch.status not in ALLOWED_TRANSITIONS[notification.status]:
            raise InvalidTransition(f"{notification.status} -> {patch.status}")
        notification.status = patch.status
        if patch.status == "acknowledged":
            notification.acknowledged_at = now
        if patch.status == "resolved":
            notification.resolved_at = now
            if notification.acknowledged_at is None:
                notification.acknowledged_at = now
        if notification.read_at is None:
            notification.read_at = now
    session.flush()
    return notification


def create_notification(session: Session, payload: NotificationCreate) -> Notification:
    notification = Notification(
        id=new_id("N"),
        type=payload.type,
        severity=payload.severity,
        title=payload.title,
        description=payload.description,
        asset_id=payload.asset_id,
        pattern_id=payload.pattern_id,
        action_id=payload.action_id,
        dedup_key=payload.dedup_key,
        status="new",
        created_at=_now(),
    )
    session.add(notification)
    session.flush()
    return notification


def within_cooldown(session: Session, dedup_key: str, cooldown_minutes: int) -> bool:
    if cooldown_minutes <= 0:
        return False
    since = _now() - timedelta(minutes=cooldown_minutes)
    statement = (
        select(DeliveryLog)
        .where(DeliveryLog.dedup_key == dedup_key, DeliveryLog.created_at >= since)
        .limit(1)
    )
    return session.scalars(statement).first() is not None


def resolve_recipients(session: Session, settings: Settings, group_ids: list[str]) -> list[str]:
    configured = read_settings(session, settings)
    emails: list[str] = []
    for group in configured.recipients:
        if group.id in group_ids and group.enabled:
            emails.extend(str(email) for email in group.emails)
    return emails


def dispatch(
    session: Session,
    settings: Settings,
    provider: EmailProvider,
    notification: Notification,
    trigger: str,
) -> list[DeliveryLog]:
    configured = read_settings(session, settings)
    logs: list[DeliveryLog] = []
    for rule in configured.rules:
        if not rule.enabled or rule.trigger != trigger:
            continue
        dedup_key = (
            f"{rule.id}:{notification.asset_id or notification.pattern_id or notification.type}"
        )
        if within_cooldown(session, dedup_key, rule.cooldown_minutes):
            continue
        for channel in rule.channels:
            if channel == "in_app":
                logs.append(
                    DeliveryLog(
                        notification_id=notification.id,
                        rule_id=rule.id,
                        channel="in_app",
                        recipient="",
                        dedup_key=dedup_key,
                        status="sent",
                    )
                )
                continue
            recipients = resolve_recipients(session, settings, rule.recipients)
            if not provider.configured:
                logs.append(
                    DeliveryLog(
                        notification_id=notification.id,
                        rule_id=rule.id,
                        channel="email",
                        recipient=",".join(recipients),
                        dedup_key=dedup_key,
                        status="failed",
                        detail="Отправка электронной почты не настроена",
                    )
                )
                continue
            for recipient in recipients:
                log = DeliveryLog(
                    notification_id=notification.id,
                    rule_id=rule.id,
                    channel="email",
                    recipient=recipient,
                    dedup_key=dedup_key,
                    status="pending",
                )
                try:
                    provider.send(
                        recipient,
                        f"VENA · {notification.title}",
                        alert_body(
                            settings.public_url,
                            notification.asset_id or "—",
                            notification.severity,
                            "24 ч" if trigger == "risk_horizon_24h" else "72 ч",
                            notification.description,
                        ),
                    )
                    log.status = "sent"
                except Exception as error:  # noqa: BLE001
                    log.status = "failed"
                    log.detail = str(error)[:500]
                logs.append(log)
    for log in logs:
        session.add(log)
    session.flush()
    return logs
