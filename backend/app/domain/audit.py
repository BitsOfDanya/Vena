from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog


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
    entry = AuditLog(
        at=datetime.now(tz=UTC),
        actor=actor,
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
