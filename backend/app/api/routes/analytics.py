from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal
from app.db.session import get_session
from app.domain import analytics as analytics_service
from app.domain import report as report_service
from app.domain.predictions import get_prediction_source
from app.schemas.analytics import EffectReport, ObjectNode

router = APIRouter(tags=["analytics"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _source(settings: Settings):
    source = get_prediction_source(settings)
    if not source.available:
        raise HTTPException(status_code=503, detail="prediction snapshot is not available")
    return source


@router.get("/assets/tree", response_model=list[ObjectNode])
def asset_tree(settings: SettingsDep, _: ReaderDep) -> list[ObjectNode]:
    """Objects and their sections from the SMVU tags, ordered from the least healthy."""
    return analytics_service.asset_tree(_source(settings))


@router.get("/analytics/effect", response_model=EffectReport)
def effect(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> EffectReport:
    return analytics_service.effect(session, settings, _source(settings))


@router.get("/reports/management.xlsx")
def management_report(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> Response:
    content = report_service.management_report(session, settings, _source(settings))
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="vena-management-report.xlsx"'},
    )
