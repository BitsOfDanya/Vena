from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.domain import system as service
from app.schemas.system import HealthComponents, Situation, SystemNotice

router = APIRouter(tags=["system"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/system/notices", response_model=list[SystemNotice])
def system_notices(settings: SettingsDep) -> list[SystemNotice]:
    return service.system_notices(settings)


@router.get("/system/components", response_model=HealthComponents)
def system_components(settings: SettingsDep) -> HealthComponents:
    return service.health_components(settings)


@router.get("/situations", response_model=list[Situation])
def situations(session: SessionDep, settings: SettingsDep) -> list[Situation]:
    return service.situations(session, settings)
