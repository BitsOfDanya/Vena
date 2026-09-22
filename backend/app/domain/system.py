from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Notification
from app.schemas.system import HealthComponents, Situation, SystemNotice


def _ml_available(settings: Settings) -> bool:
    return (settings.ml_dir / "results" / "directions.json").is_file()


def _models_available(settings: Settings) -> bool:
    models = settings.ml_dir / "configs" / "models"
    return models.is_dir() and any(models.glob("*.json"))


def health_components(settings: Settings) -> HealthComponents:
    return HealthComponents(
        api="ok",
        ml="ok" if _models_available(settings) else "unavailable",
        data="ok" if _ml_available(settings) else "unavailable",
        spatial="not_configured",
        notification_service="configured" if settings.smtp_configured else "not_configured",
        last_prediction_at=None,
        last_event_at=None,
    )


def system_notices(settings: Settings) -> list[SystemNotice]:
    notices: list[SystemNotice] = []
    if not _models_available(settings):
        notices.append(
            SystemNotice(
                id="model-unavailable",
                kind="model_unavailable",
                severity="critical",
                title="Model artifacts unavailable",
                description="Прогнозы недоступны: каталог моделей не смонтирован.",
                href="/settings/integrations",
                dismissible=False,
            )
        )
    if not _ml_available(settings):
        notices.append(
            SystemNotice(
                id="data-unavailable",
                kind="data_delayed",
                severity="attention",
                title="Result tables unavailable",
                description="Таблицы результатов ML не найдены в смонтированном каталоге.",
                href="/settings/integrations",
                dismissible=True,
            )
        )
    return notices


def situations(session: Session, settings: Settings) -> list[Situation]:
    open_actions = {
        action.asset_id: action
        for action in session.scalars(
            select(Action).where(
                Action.status.in_(("suggested", "planned", "assigned", "in_progress", "waiting"))
            )
        )
    }
    result: list[Situation] = []
    notifications = session.scalars(
        select(Notification)
        .where(Notification.type.in_(("risk", "pattern")), Notification.status != "resolved")
        .order_by(Notification.created_at.desc())
        .limit(20)
    )
    for notification in notifications:
        action = open_actions.get(notification.asset_id or "")
        status = "new"
        if action is not None:
            status = "action_created"
        elif notification.status == "acknowledged":
            status = "acknowledged"
        result.append(
            Situation(
                id=f"situation-{notification.id}",
                type="pattern" if notification.type == "pattern" else "risk",
                severity="critical" if notification.severity == "critical" else "attention",
                title=notification.title,
                summary=notification.description,
                asset_ids=[notification.asset_id] if notification.asset_id else [],
                pattern_id=notification.pattern_id,
                risk_score=None,
                risk_delta=None,
                forecast_horizon=None,
                primary_reason=notification.description,
                status=status,  # type: ignore[arg-type]
                updated_at=notification.acknowledged_at or notification.created_at,
                open_action_id=action.id if action else None,
                notification_id=notification.id,
            )
        )
    return result


def now() -> datetime:
    return datetime.now(tz=UTC)
