from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal
from app.db.session import get_session
from app.domain import analytics as analytics_service
from app.domain import report as report_service
from app.domain.predictions import get_prediction_source
from app.schemas.analytics import EffectReport, EventTypeStats, InspectionPlan, ObjectNode

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
    return analytics_service.asset_tree(_source(settings))


@router.get("/analytics/effect", response_model=EffectReport)
def effect(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> EffectReport:
    return analytics_service.effect(session, settings, _source(settings))


@router.get("/analytics/event-types", response_model=list[EventTypeStats])
def event_types(settings: SettingsDep, _: ReaderDep) -> list[EventTypeStats]:
    return analytics_service.event_types(settings, get_prediction_source(settings))


@router.get("/analytics/inspection-plan", response_model=InspectionPlan)
def inspection_plan(
    session: SessionDep,
    settings: SettingsDep,
    _: ReaderDep,
    model_id: Annotated[str, Query(pattern="^[a-z0-9_]+$")] = "pump_72h",
    count: Annotated[int, Query(ge=1, le=50)] = 5,
) -> InspectionPlan:
    """Today's inspection list for one model; fans skip channels worked on in the last day."""
    if model_id not in analytics_service.PLAN_MODELS:
        raise HTTPException(status_code=404, detail="no inspection plan for this model")
    now = datetime.now(tz=UTC)
    return analytics_service.inspection_plan(session, _source(settings), model_id, count, now)


@router.get("/analytics/weather")
def weather(settings: SettingsDep, _: ReaderDep) -> dict[str, Any]:
    """Moscow weather forecast (Open-Meteo) and how weather relates to chamber flooding."""
    source = get_prediction_source(settings)
    seasonality = analytics_service.read_report(settings, "seasonality") or {}
    return {
        "source": "Open-Meteo",
        "forecast": source.weather_forecast() if source.available else [],
        "flooding_vs_weather": seasonality.get("flooding_vs_weather", {}),
    }


@router.get("/analytics/alarm-kpis")
def alarm_kpis(settings: SettingsDep, _: ReaderDep) -> dict[str, Any]:
    """Alarm load by ISA-18.2: rate per hour, floods, bad actors, chattering channels."""
    report = analytics_service.read_report(settings, "alarm_kpis")
    if report is None:
        raise HTTPException(status_code=404, detail="alarm KPIs have not been computed")
    return report


@router.get("/analytics/health-history")
def health_history(settings: SettingsDep, _: ReaderDep) -> dict[str, Any]:
    """Daily health index of every object over the recent half-year."""
    report = analytics_service.read_report(settings, "health_history")
    if report is None:
        raise HTTPException(status_code=404, detail="health history has not been computed")
    return {"period": report.get("period"), "objects": report.get("objects", {})}


@router.get("/analytics/health-history/{group}")
def section_health_history(group: str, settings: SettingsDep, _: ReaderDep) -> list[list[Any]]:
    """Daily health index of one section (location group of the SMVU tag)."""
    report = analytics_service.read_report(settings, "health_history") or {}
    series = report.get("sections", {}).get(group)
    if series is None:
        raise HTTPException(status_code=404, detail="no history for this section")
    return list(series)


@router.get("/reports/management.xlsx")
def management_report(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> Response:
    content = report_service.management_report(session, settings, _source(settings))
    return Response(
        content=content,
        media_type=XLSX,
        headers={"Content-Disposition": 'attachment; filename="vena-management-report.xlsx"'},
    )


@router.get("/reports/predictions.csv")
def predictions_csv(settings: SettingsDep, _: ReaderDep) -> Response:
    content = report_service.predictions_csv(_source(settings).all())
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vena-predictions.csv"'},
    )


@router.get("/reports/predictions.xml")
def predictions_xml(settings: SettingsDep, _: ReaderDep) -> Response:
    source = _source(settings)
    content = report_service.predictions_xml(source.all(), source.status().snapshot_id)
    return Response(content=content, media_type="application/xml")
