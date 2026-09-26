from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, PredictionPoint, ProcessedSnapshot
from app.domain import actions as action_service
from app.domain import notifications as notification_service
from app.domain.email import EmailProvider
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


def _has_open_forecast_action(session: Session, prediction: Prediction) -> bool:
    statement = (
        select(Action.id)
        .where(
            Action.asset_id == prediction.asset_id,
            Action.status.in_(action_service.OPEN_STATUSES),
            Action.source == "vena_forecast",
        )
        .limit(1)
    )
    if prediction.id:
        by_prediction = session.scalars(
            select(Action.id)
            .where(
                Action.source_prediction_id == prediction.id,
                Action.status.in_(action_service.OPEN_STATUSES),
            )
            .limit(1)
        ).first()
        if by_prediction is not None:
            return True
    if prediction.model_id:
        by_model = session.scalars(
            select(Action.id)
            .where(
                Action.asset_id == prediction.asset_id,
                Action.source_model_id == prediction.model_id,
                Action.status.in_(action_service.OPEN_STATUSES),
            )
            .limit(1)
        ).first()
        if by_model is not None:
            return True
    return session.scalars(statement).first() is not None


def _suggest_action(session: Session, prediction: Prediction) -> bool:
    if _has_open_forecast_action(session, prediction):
        return False
    horizon = prediction.horizon_hours or 24
    priority = PRIORITY_FOR_LEVEL.get(prediction.risk_level, "medium")
    action_service.create_action(
        session,
        ActionCreate(
            asset_id=prediction.asset_id,
            kind="inspect",
            reason=(
                f"ML {prediction.model_id}: {prediction.risk_level} risk "
                f"score {prediction.score:.3f} over {horizon}h"
            ),
            priority=priority,  # type: ignore[arg-type]
            recommended_at=prediction.prediction_time + timedelta(hours=horizon),
            assignee="Дежурный инженер",
            note="Auto-draft from prediction ingest",
            source="vena_forecast",
            source_detail=prediction.model_id,
            status="suggested",
            source_prediction_id=prediction.id,
            source_model_id=prediction.model_id,
            source_prediction_time=prediction.prediction_time,
            source_score=prediction.score,
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
    significant = [item for item in predictions if item.risk_level in RULE_FOR_LEVEL]
    significant.sort(key=lambda item: item.score, reverse=True)
    for prediction in significant[: settings.prediction_critical_limit]:
        trigger = RULE_FOR_LEVEL[prediction.risk_level]
        dedup_key = f"{trigger}:{prediction.asset_id}"
        if not notification_service.within_cooldown(
            session, dedup_key, settings.prediction_cooldown_minutes
        ):
            change = (
                f", {prediction.score_delta:+.3f} since the previous snapshot"
                if prediction.score_delta is not None
                else ""
            )
            notification = notification_service.create_notification(
                session,
                NotificationCreate(
                    type="risk",
                    severity="critical" if prediction.risk_level == "critical" else "attention",
                    title=f"{prediction.asset_id} · {prediction.model_id} {prediction.score:.3f}",
                    description=(
                        f"Model {prediction.model_id} reports {prediction.risk_level} risk "
                        f"for the next {prediction.horizon_hours}h{change}."
                    ),
                    asset_id=prediction.asset_id,
                    dedup_key=dedup_key,
                ),
            )
            notification_service.dispatch(session, settings, provider, notification, trigger)
            created += 1
        if _suggest_action(session, prediction):
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
