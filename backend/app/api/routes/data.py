from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ImportBatch, InfrastructureObject, SensorChannel, TelemetryEvent
from app.db.session import get_session

router = APIRouter(prefix="/data", tags=["data"])
SessionDep = Annotated[Session, Depends(get_session)]


class DataSummary(BaseModel):
    objects: int
    channels: int
    events: int
    imports: int
    last_event_at: datetime | None


class ActivityPoint(BaseModel):
    day: str
    count: int


class ObjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    system_name: str
    tag: str


class ChannelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    object_tag: str
    channel_type: str
    display_name: str


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_record_id: str
    channel_id: str
    channel_type: str
    value_raw: str
    value_numeric: float | None
    occurred_at: datetime


@router.get("/summary", response_model=DataSummary)
def summary(session: SessionDep) -> DataSummary:
    return DataSummary(
        objects=session.scalar(select(func.count()).select_from(InfrastructureObject)) or 0,
        channels=session.scalar(select(func.count()).select_from(SensorChannel)) or 0,
        events=session.scalar(select(func.count()).select_from(TelemetryEvent)) or 0,
        imports=session.scalar(select(func.count()).select_from(ImportBatch)) or 0,
        last_event_at=session.scalar(select(func.max(TelemetryEvent.occurred_at))),
    )


@router.get("/activity", response_model=list[ActivityPoint])
def activity(session: SessionDep) -> list[ActivityPoint]:
    day = func.date(TelemetryEvent.occurred_at)
    rows = session.execute(
        select(day, func.count(TelemetryEvent.id))
        .group_by(day)
        .order_by(day.desc())
        .limit(14)
    ).all()
    return [ActivityPoint(day=str(row[0]), count=row[1]) for row in reversed(rows)]


@router.get("/objects", response_model=list[ObjectOut])
def objects(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[InfrastructureObject]:
    return list(
        session.scalars(
            select(InfrastructureObject).order_by(InfrastructureObject.name).limit(limit)
        )
    )


@router.get("/channels", response_model=list[ChannelOut])
def channels(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[SensorChannel]:
    return list(session.scalars(select(SensorChannel).order_by(SensorChannel.id).limit(limit)))


@router.get("/events", response_model=list[EventOut])
def events(
    session: SessionDep,
    channel_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[TelemetryEvent]:
    statement = select(TelemetryEvent).order_by(TelemetryEvent.occurred_at.desc()).limit(limit)
    if channel_id:
        statement = statement.where(TelemetryEvent.channel_id == channel_id)
    return list(session.scalars(statement))
