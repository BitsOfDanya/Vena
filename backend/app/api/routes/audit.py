from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_dispatcher
from app.db.models import AuditLog, User
from app.db.session import get_session

router = APIRouter(prefix="/audit", tags=["audit"])
SessionDep = Annotated[Session, Depends(get_session)]
DispatcherDep = Annotated[User, Depends(require_dispatcher)]


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor_id: str | None
    method: str
    path: str
    status_code: int
    occurred_at: datetime


@router.get("", response_model=list[AuditOut])
def list_audit(
    session: SessionDep,
    _dispatcher: DispatcherDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditLog]:
    return list(session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)))
