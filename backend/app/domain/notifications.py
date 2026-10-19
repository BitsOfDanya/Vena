from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import ColumnElement, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, DeliveryLog, Notification
from app.domain.email import LEVELS, EmailProvider, Letter, build_email_provider, vena_link
from app.domain.incidents import (
    LEVEL_RANK,
    SCENARIO_LABELS,
    location_label,
    reason_text,
    score_text,
)
from app.domain.mail_queue import enqueue
from app.domain.predictions import get_prediction_source
from app.domain.recommendations import driver_hints, recommend
from app.domain.settings_store import read_settings
from app.schemas.notifications import NotificationCreate, NotificationPatch, NotificationRule
from app.schemas.predictions import Prediction

ALLOWED_TRANSITIONS = {
    "new": {"acknowledged", "resolved"},
    "acknowledged": {"resolved"},
    "resolved": set[str](),
}

KICKERS = {
    "risk": "Прогноз инцидента",
    "pattern": "Повторяющаяся связка",
    "action": "Работа",
    "system": "Состояние системы",
    "integration": "Журнал событий",
}
KIND_LABELS = {
    "inspect": "Осмотр",
    "electrical diagnostic": "Электродиагностика",
    "service": "Обслуживание",
    "verify": "Проверка",
}
PRIORITY_LABELS = {"high": "Высокий", "medium": "Средний", "low": "Низкий"}
STATUS_LABELS = {
    "suggested": "Предложено",
    "planned": "В плане",
    "assigned": "Назначено",
    "in_progress": "В работе",
    "waiting": "Ожидание",
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
    visible: ColumnElement[bool] | None = None,
) -> list[Notification]:
    statement = select(Notification).order_by(Notification.created_at.desc())
    if visible is not None:
        statement = statement.where(visible)
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
        .where(
            DeliveryLog.dedup_key == dedup_key,
            DeliveryLog.created_at >= since,
            DeliveryLog.status.in_(("sent", "pending")),
        )
        .limit(1)
    )
    return session.scalars(statement).first() is not None


def resolve_recipients(session: Session, settings: Settings, group_ids: list[str]) -> list[str]:
    configured = read_settings(session, settings)
    emails: list[str] = []
    for group in configured.recipients:
        if group.id in group_ids and group.enabled:
            emails.extend(str(email) for email in group.emails)
    return sorted(set(emails))


def enabled_rule(session: Session, settings: Settings, trigger: str) -> NotificationRule | None:
    rules = read_settings(session, settings).rules
    return next((rule for rule in rules if rule.enabled and rule.trigger == trigger), None)


def notification_link(settings: Settings, notification: Notification) -> str:
    if notification.action_id:
        return vena_link(settings.public_url, "/actions", action=notification.action_id)
    if notification.type == "system":
        return vena_link(settings.public_url, "/settings/integrations")
    if notification.type == "integration":
        return vena_link(settings.public_url, "/journal")
    return vena_link(settings.public_url, "/pulse", notification=notification.id)


def _lead(settings: Settings, notification: Notification) -> Prediction | None:
    if notification.type != "risk" or not notification.asset_id:
        return None
    source = get_prediction_source(settings)
    candidates = [item for item in source.all() if item.asset_id == notification.asset_id]
    named = [item for item in candidates if item.model_id in notification.title]
    return min(
        named or candidates,
        key=lambda item: (LEVEL_RANK[item.risk_level], -item.score),
        default=None,
    )


def notification_letter(settings: Settings, notification: Notification) -> Letter:
    facts = [("Уровень", LEVELS.get(notification.severity, notification.severity))]
    notes: list[tuple[str, str]] = []
    lead = _lead(settings, notification)
    if lead is None:
        if notification.asset_id:
            facts.append(("Канал", notification.asset_id))
    else:
        horizon = f"{lead.horizon_hours} ч" if lead.horizon_hours else "не указан"
        calibrated = lead.score_type == "calibrated_probability"
        score = score_text(lead) if calibrated else f"{lead.score:.3f}"
        facts += [
            ("Вероятность" if calibrated else "Оценка модели", f"{score} за {horizon}"),
            ("Горизонт", horizon),
            ("Объект", location_label(lead.location_group) or lead.object_id or "не указан"),
            ("Канал", f"{lead.name} · {lead.asset_id}" if lead.name else lead.asset_id),
            ("Сценарий", SCENARIO_LABELS.get(lead.scenario, lead.scenario)),
        ]
        notes.append(("Причина", reason_text(lead, driver_hints(settings))))
        advice = recommend(settings, lead.scenario, lead)
        if advice is not None and advice.actions:
            notes.append(("Первый шаг", advice.actions[0]))
        if advice is not None and advice.consequence:
            notes.append(("Если не отреагировать", advice.consequence))
    return Letter(
        kicker=KICKERS.get(notification.type, "Уведомление"),
        title=notification.title,
        link=notification_link(settings, notification),
        tone=notification.severity,
        summary=notification.description,
        facts=facts,
        notes=notes,
    )


def _due(settings: Settings, action: Action) -> str:
    return f"{action.recommended_at.astimezone(ZoneInfo(settings.timezone)):%d.%m.%Y %H:%M}"


def action_letter(settings: Settings, action: Action, kicker: str, tone: str) -> Letter:
    return Letter(
        kicker=kicker,
        title=f"{KIND_LABELS.get(action.kind, action.kind)} · канал {action.asset_id}",
        link=vena_link(settings.public_url, "/actions", action=action.id),
        tone=tone,
        summary=action.reason,
        facts=[
            ("Работа", action.id),
            ("Исполнитель", action.assignee or "не назначен"),
            ("Срок", _due(settings, action)),
            ("Приоритет", PRIORITY_LABELS.get(action.priority, action.priority)),
            ("Статус", STATUS_LABELS.get(action.status, action.status)),
        ],
        notes=[("Примечание", action.note)] if action.note else [],
    )


def dispatch(
    session: Session,
    settings: Settings,
    provider: EmailProvider,
    notification: Notification,
    trigger: str,
    *,
    allow_email: bool = True,
    channels: Collection[str] | None = None,
    letter: Letter | None = None,
) -> list[DeliveryLog]:
    session.execute(text("SELECT pg_advisory_xact_lock(74918231)"))
    configured = read_settings(session, settings)
    logs: list[DeliveryLog] = []
    addressed: set[str] = set()
    for rule in configured.rules:
        if not rule.enabled or rule.trigger != trigger:
            continue
        dedup_key = (
            f"{rule.id}:{notification.asset_id or notification.pattern_id or notification.type}"
        )
        if within_cooldown(session, dedup_key, rule.cooldown_minutes):
            continue
        active = rule.channels if channels is None else channels
        if "in_app" in active:
            log = DeliveryLog(
                notification_id=notification.id,
                rule_id=rule.id,
                channel="in_app",
                recipient="",
                dedup_key=dedup_key,
                status="sent",
            )
            session.add(log)
            logs.append(log)
        if "email" not in active or not allow_email:
            continue
        recipients = resolve_recipients(session, settings, rule.recipients)
        if not recipients:
            log = DeliveryLog(
                notification_id=notification.id,
                rule_id=rule.id,
                channel="email",
                recipient="",
                dedup_key=dedup_key,
                status="skipped",
                detail="Не заданы получатели для правила",
            )
            session.add(log)
            logs.append(log)
        for recipient in recipients:
            if recipient in addressed:
                continue
            addressed.add(recipient)
            letter = letter or notification_letter(settings, notification)
            logs.append(
                enqueue(
                    session,
                    recipient,
                    f"VENA · {notification.title}",
                    letter.text(),
                    html=letter.html(),
                    notification_id=notification.id,
                    rule_id=rule.id,
                    dedup_key=dedup_key,
                )
            )
    session.flush()
    return logs


def notify_action(
    session: Session,
    settings: Settings,
    action: Action,
    trigger: str,
    *,
    channels: Collection[str] | None = None,
    dedup_key: str | None = None,
) -> Notification | None:
    rule = enabled_rule(session, settings, trigger)
    if rule is None:
        return None
    overdue = trigger == "action_overdue"
    notification = create_notification(
        session,
        NotificationCreate(
            type="action",
            severity=rule.severity,
            title=(
                f"Работа просрочена: {action.id} · {action.asset_id}"
                if overdue
                else f"Назначена работа {action.id} · {action.asset_id}"
            ),
            description=(
                f"Исполнитель: {action.assignee or 'не назначен'}. "
                f"Срок: {_due(settings, action)}. {action.reason}"
            ).strip(),
            asset_id=action.asset_id,
            action_id=action.id,
            dedup_key=dedup_key,
        ),
    )
    dispatch(
        session,
        settings,
        build_email_provider(settings),
        notification,
        trigger,
        channels=channels,
        letter=action_letter(
            settings,
            action,
            "Работа просрочена" if overdue else "Работа назначена",
            rule.severity,
        ),
    )
    return notification


def notify_events(
    session: Session,
    settings: Settings,
    count: int,
    alarms: int,
    description: str,
    asset_id: str | None = None,
) -> None:
    if not count:
        return
    notification = create_notification(
        session,
        NotificationCreate(
            type="integration",
            severity="attention" if alarms else "info",
            title="Тревожные события оборудования" if alarms else "Новые события журнала",
            description=f"Принято новых событий: {count}. Тревожных: {alarms}. {description}",
            asset_id=asset_id,
        ),
    )
    dispatch(
        session,
        settings,
        build_email_provider(settings),
        notification,
        "alarm_event" if alarms else "new_events",
    )
