from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import smvu as smvu_service

router = APIRouter(prefix="/smvu", tags=["smvu"])

SessionDep = Annotated[Session, Depends(get_session)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
WriterDep = Annotated[Principal, Depends(require_min_role("dispatcher"))]


class SmvuStatus(BaseModel):
    configured: bool
    last_batch_id: str | None = None
    last_event_count: int = 0
    last_event_at: datetime | None = None
    received_at: datetime | None = None
    age_seconds: int | None = None
    fresh: bool = False
    detail: str = ""


class SmvuBatchIn(BaseModel):
    batch_id: str = Field(min_length=1, max_length=80)
    event_count: int = Field(ge=0, le=1_000_000)
    last_event_at: datetime | None = None
    detail: str = ""


@router.get("/status", response_model=SmvuStatus)
def smvu_status(session: SessionDep, _: ReaderDep) -> SmvuStatus:
    return SmvuStatus.model_validate(smvu_service.get_status(session))


@router.post("/events", response_model=SmvuStatus, status_code=status.HTTP_202_ACCEPTED)
def ingest_smvu_batch(
    body: SmvuBatchIn,
    session: SessionDep,
    principal: WriterDep,
) -> SmvuStatus:
    """Accept a SMVU event-batch acknowledgement.

    Full event persistence and scoring remain offline (`score_snapshot`);
    this endpoint records freshness for the ≤5 min operational target.
    """
    result = smvu_service.accept_batch(
        session,
        batch_id=body.batch_id,
        event_count=body.event_count,
        last_event_at=body.last_event_at,
        detail=body.detail,
    )
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="smvu.ingest",
        resource_type="smvu_batch",
        resource_id=body.batch_id,
        detail=f"events={body.event_count}",
    )
    return SmvuStatus.model_validate(result)
