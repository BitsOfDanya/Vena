from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal
from app.domain import incident_registry as service
from app.domain.scopes import ScopeDep
from app.schemas.incidents import IncidentRegistry, ObjectRiskList

router = APIRouter(prefix="/incidents", tags=["incidents"])

SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]


@router.get("/registry", response_model=IncidentRegistry)
def incident_registry(
    settings: SettingsDep,
    _: ReaderDep,
    scope: ScopeDep,
    kind: Literal["fire", "flood", "power"] | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
) -> IncidentRegistry:
    return service.registry(settings, scope, kind=kind, limit=limit)


@router.get("/objects", response_model=ObjectRiskList)
def object_risks(
    settings: SettingsDep,
    _: ReaderDep,
    scope: ScopeDep,
    scenario: Annotated[str | None, Query(max_length=40)] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> ObjectRiskList:
    return service.object_risks(settings, scope, scenario=scenario or None, limit=limit)
