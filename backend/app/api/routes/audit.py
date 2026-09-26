from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import Principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.schemas.audit import AuditEntry

router = APIRouter(tags=["audit"])

SessionDep = Annotated[Session, Depends(get_session)]
AdminDep = Annotated[Principal, Depends(require_min_role("admin"))]


@router.get("/audit", response_model=list[AuditEntry])
def list_audit_log(
    session: SessionDep,
    _: AdminDep,
    actor: str | None = None,
    action: str | None = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[AuditEntry]:
    return [
        AuditEntry.model_validate(entry)
        for entry in audit_service.list_audit(session, actor=actor, action=action, limit=limit)
    ]
