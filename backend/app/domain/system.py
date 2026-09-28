from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Notification
from app.domain.actions import OPEN_STATUSES
from app.domain.health import load_calibration, location_health
from app.domain.incidents import group_incidents, location_label, reason_text, score_text
from app.domain.predictions import get_prediction_source
from app.domain.recommendations import recommend
from app.schemas.predictions import Prediction
from app.schemas.system import HealthComponents, LocationHistory, Situation, SystemNotice

# Deterministic product priority: risk level first, then score change, then
# the shortest forecast horizon, then the newest prediction.
LEVEL_RANK = {"critical": 0, "attention": 1, "observe": 2, "normal": 3}


def _models_available(settings: Settings) -> bool:
    models = settings.ml_dir / "configs" / "models"
    return models.is_dir() and any(models.glob("*.json"))


def _results_available(settings: Settings) -> bool:
    return (settings.ml_dir / "results" / "directions.json").is_file()


def health_components(settings: Settings) -> HealthComponents:
    status = get_prediction_source(settings).status()
    if not status.available:
        ml_state = "unavailable"
    elif status.stale:
        ml_state = "stale"
    else:
        ml_state = "ok"
    return HealthComponents(
        api="ok",
        ml=ml_state if _models_available(settings) else "unavailable",
        data="ok" if _results_available(settings) else "unavailable",
        spatial="not_configured",
        notification_service="configured" if settings.smtp_configured else "not_configured",
        last_prediction_at=status.prediction_time,
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
    status = get_prediction_source(settings).status()
    if not status.available:
        notices.append(
            SystemNotice(
                id="predictions-unavailable",
                kind="model_unavailable",
                severity="critical",
                title="ML predictions unavailable",
                description="Снимок прогнозов не найден. Риски и ситуации не рассчитываются.",
                href="/settings/integrations",
                dismissible=False,
            )
        )
    elif status.stale and status.age_seconds is not None:
        days = status.age_seconds // 86_400
        notices.append(
            SystemNotice(
                id="predictions-stale",
                kind="data_delayed",
                severity="attention",
                title="Prediction snapshot is outdated",
                description=(
                    f"Последний снимок прогнозов рассчитан {days} дн. назад: "
                    "журнал событий не обновлялся."
                ),
                href="/settings/integrations",
                dismissible=True,
            )
        )
    return notices


def situations(session: Session, settings: Settings, limit: int = 6) -> list[Situation]:
    source = get_prediction_source(settings)
    if not source.available:
        return []

    open_actions: dict[str, Action] = {}
    for open_action in session.scalars(select(Action).where(Action.status.in_(OPEN_STATUSES))):
        open_actions.setdefault(open_action.asset_id, open_action)

    notifications: dict[str, Notification] = {}
    for recent_notification in session.scalars(
        select(Notification)
        .where(Notification.asset_id.is_not(None), Notification.status != "resolved")
        .order_by(Notification.created_at.desc())
    ):
        if recent_notification.asset_id is not None:
            notifications.setdefault(recent_notification.asset_id, recent_notification)

    # One asset keeps only its strongest model before grouping, so a pump with
    # 24h and 72h forecasts is counted once inside its incident.
    best: dict[str, Prediction] = {}
    for prediction in source.all():
        if prediction.risk_level not in ("critical", "attention"):
            continue
        current = best.get(prediction.asset_id)
        if current is None or (LEVEL_RANK[prediction.risk_level], -prediction.score) < (
            LEVEL_RANK[current.risk_level],
            -current.score,
        ):
            best[prediction.asset_id] = prediction

    incident_probability = source.incident_probabilities()
    health = location_health(source.all(), incident_probability, load_calibration(settings.ml_dir))
    histories = source.location_history()
    result: list[Situation] = []
    for incident in group_incidents(best.values()):
        lead = incident.lead
        action = next(
            (open_actions[asset] for asset in incident.asset_ids if asset in open_actions), None
        )
        notification = next(
            (notifications[asset] for asset in incident.asset_ids if asset in notifications), None
        )
        status: str = "new"
        if action is not None:
            status = "action_created"
        elif notification is not None and notification.status == "acknowledged":
            status = "acknowledged"
        count = len(incident.asset_ids)
        scope = f"{count} channels, lead {lead.asset_id}" if count > 1 else lead.asset_id
        location_probability = (
            incident_probability.get((incident.scenario, incident.location))
            if incident.location
            else None
        )
        # The location model scores once a day, the channel model at a fresh event;
        # the chance that any channel fails is never below the lead channel's.
        if location_probability is not None and lead.score_type == "calibrated_probability":
            location_probability = max(location_probability, lead.score)
        location_text = (
            f" Location risk {location_probability:.0%} within 24h."
            if location_probability is not None
            else ""
        )
        result.append(
            Situation(
                id=f"situation-{lead.source_snapshot}:{incident.key}",
                type="risk",
                severity="critical" if incident.risk_level == "critical" else "attention",
                title=incident.title,
                summary=(
                    f"{scope}: {lead.model_id} {score_text(lead)} "
                    f"({lead.risk_level}) for the next {lead.horizon_hours}h.{location_text}"
                ),
                asset_ids=incident.asset_ids,
                pattern_id=None,
                risk_score=lead.score,
                risk_delta=lead.score_delta,
                forecast_horizon=lead.horizon_hours,
                primary_reason=reason_text(lead),
                status=status,  # type: ignore[arg-type]
                updated_at=lead.prediction_time,
                open_action_id=action.id if action else None,
                notification_id=notification.id if notification else None,
                scenario=incident.scenario,
                location=location_label(incident.location),
                asset_count=count,
                incident_probability=location_probability,
                health_index=health[incident.location].index
                if incident.location in health
                else None,
                recommendation=recommend(settings, incident.scenario, lead),
                history=_history(histories, incident.location, lead.device_type),
            )
        )

    result.sort(
        key=lambda item: (
            LEVEL_RANK["critical" if item.severity == "critical" else "attention"],
            -(item.risk_score or 0),
            item.forecast_horizon or 0,
        )
    )
    return result[:limit]


def _history(
    histories: dict[str, dict[str, dict]], group: str | None, device: str
) -> LocationHistory | None:
    raw = histories.get(group or "", {}).get(device)
    if not raw:
        return None
    try:
        return LocationHistory(**raw)
    except (TypeError, ValueError):
        return None


def now() -> datetime:
    return datetime.now(tz=UTC)
