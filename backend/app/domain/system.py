from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Notification, SmvuIngestState, SpatialLayer
from app.domain.actions import OPEN_STATUSES
from app.domain.health import load_calibration, location_health
from app.domain.incidents import (
    SCENARIO_LABELS,
    group_incidents,
    location_label,
    reason_text,
    score_text,
)
from app.domain.predictions import get_prediction_source
from app.domain.recommendations import driver_hints, recommend
from app.schemas.predictions import Prediction
from app.schemas.system import HealthComponents, LocationHistory, Situation, SystemNotice

LEVEL_RANK = {"critical": 0, "attention": 1, "observe": 2, "normal": 3}


def _models_available(settings: Settings) -> bool:
    models = settings.ml_dir / "configs" / "models"
    return models.is_dir() and any(models.glob("*.json"))


def _results_available(settings: Settings) -> bool:
    return (settings.ml_dir / "results" / "directions.json").is_file()


def health_components(settings: Settings, session: Session) -> HealthComponents:
    status = get_prediction_source(settings).status()
    if not status.available:
        ml_state = "unavailable"
    elif status.stale:
        ml_state = "stale"
    else:
        ml_state = "ok"
    spatial = session.get(SpatialLayer, "default")
    stream = session.get(SmvuIngestState, "default")
    return HealthComponents(
        api="ok",
        ml=ml_state if _models_available(settings) else "unavailable",
        data="ok" if _results_available(settings) else "unavailable",
        spatial="configured" if spatial else "not_configured",
        notification_service="configured" if settings.smtp_configured else "not_configured",
        last_prediction_at=status.prediction_time,
        last_event_at=stream.last_event_at if stream else None,
    )


def system_notices(settings: Settings) -> list[SystemNotice]:
    notices: list[SystemNotice] = []
    if not _models_available(settings):
        notices.append(
            SystemNotice(
                id="model-unavailable",
                kind="model_unavailable",
                severity="critical",
                title="Артефакты моделей недоступны",
                description="Прогнозы недоступны: каталог моделей не смонтирован.",
                href="/settings/integrations",
                dismissible=False,
            )
        )
    status = get_prediction_source(settings).status()
    if status.data_source == "demo":
        notices.append(
            SystemNotice(
                id="demo-source",
                kind="data_delayed",
                severity="attention",
                title="Демонстрационные данные",
                description=(
                    "Реальный журнал ещё не подключён. "
                    "Прогнозы рассчитаны на синтетических каналах."
                ),
                href="/settings/integrations",
                dismissible=False,
            )
        )
    if not status.available:
        notices.append(
            SystemNotice(
                id="predictions-unavailable",
                kind="model_unavailable",
                severity="critical",
                title="Прогнозы недоступны",
                description="Снимок прогнозов не найден. Риски и ситуации не рассчитываются.",
                href="/settings/integrations",
                dismissible=False,
            )
        )
    elif status.stale and status.age_seconds is not None:
        days = status.age_seconds // 86_400
        demo_stand = settings.environment in ("local", "test") or settings.seed_demo
        if status.data_source == "journal" and status.stream is None and status.prediction_time:
            notices.append(
                SystemNotice(
                    id="predictions-historical",
                    kind="data_delayed",
                    severity="info",
                    title="Исторический журнал",
                    description=(
                        "Журнал заказчика заканчивается "
                        f"{status.prediction_time:%d.%m.%Y}, прогнозы рассчитаны на этот момент. "
                        "Новые события СМВУ принимаются через API и пересчитываются автоматически."
                    ),
                    href="/settings/integrations",
                    dismissible=True,
                )
            )
        elif demo_stand:
            notices.append(
                SystemNotice(
                    id="predictions-stale",
                    kind="data_delayed",
                    severity="info",
                    title="Демонстрационный режим",
                    description=(
                        f"Снимок прогнозов зафиксирован {days} дн. назад. "
                        "Это демонстрационные данные стенда, а не сбой сервиса."
                    ),
                    href="/settings/integrations",
                    dismissible=True,
                )
            )
        else:
            notices.append(
                SystemNotice(
                    id="predictions-stale",
                    kind="data_delayed",
                    severity="attention",
                    title="Снимок прогнозов устарел",
                    description=(
                        f"Последний снимок рассчитан {days} дн. назад: "
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
    hints = driver_hints(settings)
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
        lead_label = lead.name or lead.asset_id
        scope = f"{count} каналов, ведущий {lead_label}" if count > 1 else lead_label
        location_probability = (
            incident_probability.get((incident.scenario, incident.location))
            if incident.location
            else None
        )
        if location_probability is not None and lead.score_type == "calibrated_probability":
            location_probability = max(location_probability, lead.score)
        location_text = (
            f" Риск локации {location_probability:.0%} на 24 ч."
            if location_probability is not None
            else ""
        )
        level_ru = {"critical": "критично", "attention": "внимание"}.get(
            lead.risk_level, lead.risk_level
        )
        result.append(
            Situation(
                id=f"situation-{lead.source_snapshot}:{incident.key}",
                type="risk",
                severity="critical" if incident.risk_level == "critical" else "attention",
                title=incident.title,
                summary=(
                    f"{scope}: {SCENARIO_LABELS.get(incident.scenario, incident.scenario)} "
                    f"{score_text(lead)} ({level_ru}) на ближайшие {lead.horizon_hours} ч."
                    f"{location_text}"
                ),
                asset_ids=incident.asset_ids,
                pattern_id=None,
                risk_score=lead.score,
                risk_delta=lead.score_delta,
                forecast_horizon=lead.horizon_hours,
                primary_reason=reason_text(lead, hints),
                status=status,  # type: ignore[arg-type]
                updated_at=lead.prediction_time,
                open_action_id=action.id if action else None,
                notification_id=notification.id if notification else None,
                scenario=incident.scenario,
                location=location_label(incident.location),
                location_group=incident.location,
                asset_count=count,
                incident_probability=location_probability,
                health_index=health[incident.location].index
                if incident.location in health
                else None,
                model_id=lead.model_id,
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
    return _diversify_by_scenario(result, limit)


def _diversify_by_scenario(items: list[Situation], limit: int) -> list[Situation]:
    if limit <= 0 or not items:
        return []
    buckets: dict[str, list[Situation]] = {}
    order: list[str] = []
    for item in items:
        key = item.scenario or "equipment"
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(item)
    selected: list[Situation] = []
    indexes = {key: 0 for key in order}
    while len(selected) < limit:
        progressed = False
        for key in order:
            index = indexes[key]
            bucket = buckets[key]
            if index < len(bucket):
                selected.append(bucket[index])
                indexes[key] = index + 1
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
    return selected


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
