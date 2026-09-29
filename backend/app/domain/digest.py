from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Notification
from app.domain.email import EmailProvider, digest_body
from app.domain.notifications import resolve_recipients
from app.domain.settings_store import read_settings


def build_sections(session: Session) -> list[tuple[str, list[str]]]:
    since = datetime.now(tz=UTC) - timedelta(days=1)
    critical = session.scalars(
        select(Notification).where(
            Notification.severity == "critical", Notification.status != "resolved"
        )
    ).all()
    patterns = session.scalars(
        select(Notification).where(Notification.type == "pattern", Notification.created_at >= since)
    ).all()
    open_actions = session.scalars(
        select(Action).where(Action.status.in_(("planned", "assigned", "in_progress", "waiting")))
    ).all()
    now = datetime.now(tz=UTC)
    overdue = [action for action in open_actions if action.recommended_at.replace(tzinfo=UTC) < now]
    completed = session.scalars(
        select(Action).where(Action.completed_at.is_not(None), Action.completed_at >= since)
    ).all()
    return [
        ("Критичные", [f"{item.title}" for item in critical]),
        ("Повторяющиеся", [f"{item.title}" for item in patterns]),
        ("Работы к сроку", [f"{item.id} · {item.asset_id}" for item in open_actions]),
        ("Просрочено", [f"{item.id} · {item.asset_id}" for item in overdue]),
        (
            "Завершено с прошлой сводки",
            [f"{item.id} · {item.result_outcome}" for item in completed],
        ),
    ]


def send_digest(session: Session, settings: Settings, provider: EmailProvider) -> int:
    configured = read_settings(session, settings)
    if not configured.digest.enabled or not provider.configured:
        return 0
    recipients = resolve_recipients(session, settings, configured.digest.recipients)
    if not recipients:
        return 0
    body = digest_body(settings.public_url, build_sections(session))
    sent = 0
    for recipient in recipients:
        try:
            provider.send(recipient, "VENA · Утренняя сводка", body)
            sent += 1
        except Exception:  # noqa: BLE001
            continue
    return sent
