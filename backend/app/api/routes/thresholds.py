from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import thresholds as threshold_service
from app.domain.predictions import get_prediction_source
from app.schemas.thresholds import ModelThresholds, ThresholdLevels, ThresholdUpdate

router = APIRouter(prefix="/ml/thresholds", tags=["ml"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
AdminDep = Annotated[Principal, Depends(require_min_role("admin"))]


def _catalogue(session: Session, settings: Settings) -> list[ModelThresholds]:
    source = get_prediction_source(settings)
    models = source.status().models if source.available else []
    return threshold_service.catalogue(session, settings, models, source.default_thresholds())


def _levels_text(levels: ThresholdLevels) -> str:
    return (
        f"критично {levels.critical:.4f}, внимание {levels.high:.4f}, "
        f"наблюдение {levels.medium:.4f}"
    )


def _find(session: Session, settings: Settings, model_id: str) -> ModelThresholds:
    item = next((item for item in _catalogue(session, settings) if item.model_id == model_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Модель не найдена")
    return item


@router.get("", response_model=list[ModelThresholds])
def list_thresholds(
    session: SessionDep, settings: SettingsDep, _: ReaderDep
) -> list[ModelThresholds]:
    return _catalogue(session, settings)


@router.put("/{model_id}", response_model=ModelThresholds)
def update_thresholds(
    model_id: str,
    payload: ThresholdUpdate,
    session: SessionDep,
    settings: SettingsDep,
    principal: AdminDep,
) -> ModelThresholds:
    previous = _find(session, settings, model_id).effective
    threshold_service.save(session, model_id, payload.model_dump())
    detail = _levels_text(payload)
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="settings.thresholds.update",
        resource_type="model",
        resource_id=model_id,
        detail=f"{detail}; было: {_levels_text(previous)}" if previous else detail,
    )
    session.commit()
    threshold_service.invalidate()
    return _find(session, settings, model_id)


@router.delete("/{model_id}", response_model=ModelThresholds)
def reset_thresholds(
    model_id: str, session: SessionDep, settings: SettingsDep, principal: AdminDep
) -> ModelThresholds:
    _find(session, settings, model_id)
    threshold_service.save(session, model_id, None)
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="settings.thresholds.reset",
        resource_type="model",
        resource_id=model_id,
    )
    session.commit()
    threshold_service.invalidate()
    return _find(session, settings, model_id)
