from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.models import Action, Notification
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import ingest as ingest_service
from app.domain.actions import OPEN_STATUSES
from app.domain.email import build_email_provider
from app.domain.predictions import get_prediction_source
from app.schemas.predictions import (
    AccessEvent,
    AlarmAssessment,
    FeedbackRow,
    ModelInfo,
    Prediction,
    PredictionDetail,
    SnapshotStatus,
)

router = APIRouter(tags=["predictions"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
ActorDep = Annotated[Principal, Depends(require_min_role("dispatcher"))]


def _require_snapshot(settings: Settings) -> None:
    source = get_prediction_source(settings)
    if not source.available:
        raise HTTPException(
            status_code=503, detail=source.status().detail or "predictions unavailable"
        )


@router.get("/predictions", response_model=list[Prediction])
def list_predictions(
    settings: SettingsDep,
    _: ReaderDep,
    asset_id: str | None = None,
    device_type: str | None = None,
    risk_level: str | None = None,
    horizon: int | None = None,
    model_id: str | None = None,
    sort: Annotated[str, Query(pattern="^(risk_desc|delta_desc|latest)$")] = "risk_desc",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Prediction]:
    _require_snapshot(settings)
    source = get_prediction_source(settings)
    return source.query(asset_id, device_type, risk_level, horizon, model_id, sort, limit, offset)


@router.get("/predictions/snapshot", response_model=SnapshotStatus)
def snapshot_status(settings: SettingsDep, _: ReaderDep) -> SnapshotStatus:
    return get_prediction_source(settings).status()


@router.post("/predictions/refresh", response_model=dict)
def refresh(
    session: SessionDep,
    settings: SettingsDep,
    principal: ActorDep,
    force: bool = False,
) -> dict:
    source = get_prediction_source(settings)
    result = ingest_service.refresh_predictions(
        session, settings, source, build_email_provider(settings), force
    )
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="predictions.refresh",
        resource_type="snapshot",
        resource_id=result.snapshot_id or "",
        detail=result.detail or "",
    )
    return {
        "processed": result.processed,
        "snapshot_id": result.snapshot_id,
        "prediction_count": result.prediction_count,
        "notifications_created": result.notifications_created,
        "actions_created": result.actions_created,
        "detail": result.detail,
    }


@router.get("/predictions/{prediction_id:path}", response_model=PredictionDetail)
def get_prediction(
    prediction_id: str, session: SessionDep, settings: SettingsDep, _: ReaderDep
) -> PredictionDetail:
    _require_snapshot(settings)
    source = get_prediction_source(settings)
    prediction = source.get(prediction_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found")
    action = session.scalars(
        select(Action)
        .where(Action.asset_id == prediction.asset_id, Action.status.in_(OPEN_STATUSES))
        .limit(1)
    ).first()
    notification = session.scalars(
        select(Notification)
        .where(Notification.asset_id == prediction.asset_id, Notification.status != "resolved")
        .order_by(Notification.created_at.desc())
        .limit(1)
    ).first()
    return PredictionDetail(
        prediction=prediction,
        model=ModelInfo(
            model_id=prediction.model_id,
            model_version=prediction.model_version,
            horizon_hours=prediction.horizon_hours,
            calibrated=prediction.score_type == "calibrated_probability",
        ),
        factors=prediction.factors,
        open_action_id=action.id if action else None,
        notification_id=notification.id if notification else None,
    )


@router.get("/assets/{asset_id}/prediction", response_model=Prediction)
def asset_prediction(asset_id: str, settings: SettingsDep, _: ReaderDep) -> Prediction:
    _require_snapshot(settings)
    prediction = get_prediction_source(settings).latest_for_asset(asset_id)
    if prediction is None:
        raise HTTPException(status_code=404, detail="prediction not found for asset")
    return prediction


@router.get("/assets/{asset_id}/predictions", response_model=list[dict])
def asset_prediction_history(
    asset_id: str,
    session: SessionDep,
    _: ReaderDep,
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[dict]:
    points = ingest_service.history(session, asset_id, start, end, limit)
    return [
        {
            "asset_id": point.asset_id,
            "model_id": point.model_id,
            "horizon_hours": point.horizon_hours,
            "score": point.score,
            "score_type": point.score_type,
            "risk_level": point.risk_level,
            "prediction_time": point.prediction_time,
            "snapshot_id": point.snapshot_id,
        }
        for point in points
    ]


@router.get("/alarms", response_model=list[AlarmAssessment])
def list_alarms(
    settings: SettingsDep,
    _: ReaderDep,
    needs_verification: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> list[AlarmAssessment]:
    _require_snapshot(settings)
    items = get_prediction_source(settings).alarms()
    if needs_verification is not None:
        items = [item for item in items if item.needs_verification == needs_verification]
    return items[:limit]


@router.get("/access-events", response_model=list[AccessEvent])
def list_access_events(
    settings: SettingsDep, _: ReaderDep, limit: Annotated[int, Query(ge=1, le=2000)] = 200
) -> list[AccessEvent]:
    _require_snapshot(settings)
    return get_prediction_source(settings).access_events()[:limit]


@router.get("/ml/feedback", response_model=list[FeedbackRow])
def feedback(
    session: SessionDep, _: ReaderDep, limit: Annotated[int, Query(ge=1, le=1000)] = 200
) -> list[FeedbackRow]:
    statement = (
        select(Action)
        .where(Action.source == "vena_forecast", Action.source_prediction_id.is_not(None))
        .order_by(Action.created_at.desc())
        .limit(limit)
    )
    return [
        FeedbackRow(
            prediction_id=action.source_prediction_id,
            asset_id=action.asset_id,
            model_id=action.source_model_id,
            prediction_time=action.source_prediction_time,
            score=action.source_score,
            horizon_hours=action.source_horizon_hours,
            action_id=action.id,
            action_status=action.status,
            action_result=action.result_outcome,
            completed_at=action.completed_at,
        )
        for action in session.scalars(statement)
    ]
