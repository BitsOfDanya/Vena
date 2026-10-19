from contextvars import ContextVar
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import client_ip
from app.db.models import AuditLog

current_request: ContextVar[Request | None] = ContextVar("audit_request", default=None)


def record(
    session: Session,
    *,
    actor: str,
    role: str,
    action: str,
    resource_type: str = "",
    resource_id: str = "",
    detail: str = "",
    ip: str | None = None,
) -> AuditLog:
    request = current_request.get()
    if ip is None and request is not None:
        ip = client_ip(request, get_settings())
    entry = AuditLog(
        at=datetime.now(tz=UTC),
        actor=actor[:120],
        role=role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip=ip,
    )
    session.add(entry)
    session.flush()
    return entry


def list_audit(
    session: Session,
    *,
    actor: str | None = None,
    action: str | None = None,
    limit: int = 200,
) -> list[AuditLog]:
    statement = select(AuditLog).order_by(AuditLog.at.desc()).limit(limit)
    if actor:
        statement = statement.where(AuditLog.actor == actor)
    if action:
        statement = statement.where(AuditLog.action == action)
    return list(session.scalars(statement))
