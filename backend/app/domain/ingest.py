from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Notification, PredictionPoint, ProcessedSnapshot
from app.domain import actions as action_service
from app.domain import notifications as notification_service
from app.domain.email import EmailProvider
from app.domain.incidents import Incident, group_incidents, reason_text, score_text
from app.domain.predictions import PredictionSource
from app.schemas.actions import ActionCreate
from app.schemas.notifications import NotificationCreate
from app.schemas.predictions import Prediction

RULE_FOR_LEVEL = {"critical": "critical_risk", "attention": "risk_horizon_24h"}
PRIORITY_FOR_LEVEL = {"critical": "high", "attention": "medium"}


@dataclass
class IngestResult:
    processed: bool
    snapshot_id: str | None
    prediction_count: int = 0
    notifications_created: int = 0
    actions_created: int = 0
    detail: str = ""


LEVEL_RU = {
    "critical": "критично",
    "attention": "внимание",
    "observe": "наблюдение",
    "normal": "норма",
}


def previous_scores(session: Session, snapshot_id: str) -> dict[tuple[str, str], float]:
    statement = (
        select(PredictionPoint)
        .where(PredictionPoint.snapshot_id != snapshot_id)
        .order_by(PredictionPoint.prediction_time.desc())
        .limit(20_000)
    )
    scores: dict[tuple[str, str], float] = {}
    for point in session.scalars(statement):
        key = (point.asset_id, point.model_id)
        if key not in scores:
            scores[key] = point.score
    return scores


def apply_deltas(
    session: Session, predictions: list[Prediction], snapshot_id: str
) -> list[Prediction]:
    previous = previous_scores(session, snapshot_id)
    for prediction in predictions:
        earlier = previous.get((prediction.asset_id, prediction.model_id))
        if earlier is None:
            continue
        prediction.previous_score = earlier
        prediction.score_delta = round(prediction.score - earlier, 6)
    return predictions


def _recently_notified(session: Session, dedup_key: str, minutes: int, now: datetime) -> bool:
    if minutes <= 0:
        return False
    statement = (
        select(Notification.id)
        .where(
            Notification.dedup_key == dedup_key,
            Notification.created_at >= now - timedelta(minutes=minutes),
        )
        .limit(1)
    )
    return session.scalars(statement).first() is not None


def _has_open_forecast_action(session: Session, asset_ids: list[str]) -> bool:
    statement = (
        select(Action.id)
        .where(
            Action.asset_id.in_(asset_ids),
            Action.status.in_(action_service.OPEN_STATUSES),
            Action.source == "vena_forecast",
        )
        .limit(1)
    )
    return session.scalars(statement).first() is not None


def _suggest_action(session: Session, incident: Incident, now: datetime) -> bool:
    if _has_open_forecast_action(session, incident.asset_ids):
        return False
    lead = incident.lead
    horizon = lead.horizon_hours or 24
    priority = PRIORITY_FOR_LEVEL.get(lead.risk_level, "medium")
    count = len(incident.asset_ids)
    scope = f"; каналов на локации: {count}" if count > 1 else ""
    action_service.create_action(
        session,
        ActionCreate(
            asset_id=lead.asset_id,
            kind="inspect",
            reason=(
                f"{incident.title}: модель {lead.model_id}, уровень "
                f"{LEVEL_RU.get(lead.risk_level, lead.risk_level)}, вероятность "
                f"{score_text(lead)} за {horizon} ч{scope}"
            ),
            priority=priority,  # type: ignore[arg-type]
            recommended_at=max(lead.prediction_time, now) + timedelta(hours=horizon),
            assignee="Дежурный инженер",
            note="Черновик создан по прогнозу модели",
            source="vena_forecast",
            source_detail=lead.model_id,
            status="suggested",
            source_prediction_id=lead.id,
            source_model_id=lead.model_id,
            source_prediction_time=lead.prediction_time,
            source_score=lead.score,
            source_horizon_hours=horizon,
        ),
        actor="vena-ingest",
    )
    return True


def refresh_predictions(
    session: Session,
    settings: Settings,
    source: PredictionSource,
    provider: EmailProvider,
    force: bool = False,
) -> IngestResult:
    status = source.status()
    if not status.available or status.snapshot_id is None:
        return IngestResult(
            processed=False, snapshot_id=None, detail=status.detail or "snapshot unavailable"
        )

    existing = session.get(ProcessedSnapshot, status.snapshot_id)
    if existing is not None and not force:
        return IngestResult(
            processed=False,
            snapshot_id=status.snapshot_id,
            prediction_count=existing.prediction_count,
            detail="snapshot already processed",
        )

    predictions = apply_deltas(session, source.all(), status.snapshot_id)

    if existing is None:
        for prediction in predictions:
            if prediction.previous_score is not None and prediction.score_delta == 0:
                continue
            session.add(
                PredictionPoint(
                    snapshot_id=status.snapshot_id,
                    asset_id=prediction.asset_id,
                    model_id=prediction.model_id,
                    horizon_hours=prediction.horizon_hours,
                    score=prediction.score,
                    score_type=prediction.score_type,
                    risk_level=prediction.risk_level,
                    prediction_time=prediction.prediction_time,
                )
            )

    created = 0
    actions_created = 0
    now = datetime.now(tz=UTC)
    significant = [item for item in predictions if item.risk_level in RULE_FOR_LEVEL]
    per_scenario: dict[str, int] = {}
    for incident in group_incidents(significant):
        if per_scenario.get(incident.scenario, 0) >= settings.prediction_critical_limit:
            continue
        per_scenario[incident.scenario] = per_scenario.get(incident.scenario, 0) + 1
        lead = incident.lead
        trigger = RULE_FOR_LEVEL[lead.risk_level]
        dedup_key = f"{trigger}:{incident.key}"
        if not _recently_notified(session, dedup_key, settings.prediction_cooldown_minutes, now):
            change = (
                f", изменение {lead.score_delta:+.3f} с прошлого снимка"
                if lead.score_delta is not None
                else ""
            )
            count = len(incident.asset_ids)
            scope = f" Риск разделяют каналов на локации: {count}." if count > 1 else ""
            notification = notification_service.create_notification(
                session,
                NotificationCreate(
                    type="risk",
                    severity="critical" if lead.risk_level == "critical" else "attention",
                    title=f"{incident.title} · {lead.model_id} {score_text(lead)}",
                    description=(
                        f"Модель {lead.model_id}: уровень "
                        f"{LEVEL_RU.get(lead.risk_level, lead.risk_level)} на "
                        f"{lead.horizon_hours} ч{change}.{scope} "
                        f"Главная причина: {reason_text(lead)}."
                    ),
                    asset_id=lead.asset_id,
                    dedup_key=dedup_key,
                ),
            )
            notification_service.dispatch(
                session,
                settings,
                provider,
                notification,
                trigger,
                allow_email=status.data_source == "journal",
            )
            created += 1
        if _suggest_action(session, incident, now):
            actions_created += 1

    if existing is None:
        session.add(
            ProcessedSnapshot(
                snapshot_id=status.snapshot_id,
                prediction_time=status.prediction_time,
                prediction_count=len(predictions),
                notifications_created=created,
                stale=status.stale,
                processed_at=datetime.now(tz=UTC),
            )
        )
    else:
        existing.notifications_created += created
        existing.processed_at = datetime.now(tz=UTC)
    session.flush()

    return IngestResult(
        processed=True,
        snapshot_id=status.snapshot_id,
        prediction_count=len(predictions),
        notifications_created=created,
        actions_created=actions_created,
    )


def history(
    session: Session,
    asset_id: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 200,
) -> list[PredictionPoint]:
    statement = (
        select(PredictionPoint)
        .where(PredictionPoint.asset_id == asset_id)
        .order_by(PredictionPoint.prediction_time.desc())
    )
    if start is not None:
        statement = statement.where(PredictionPoint.prediction_time >= start)
    if end is not None:
        statement = statement.where(PredictionPoint.prediction_time <= end)
    return list(session.scalars(statement.limit(limit)))
