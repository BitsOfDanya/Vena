from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.auth import COOKIE_NAME, token_user_id
from app.core.config import get_settings
from app.db.models import AuditLog
from app.db.session import get_session


def audit_mutation(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> Iterator[None]:
    yield
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    route_status = getattr(request.scope.get("route"), "status_code", None)
    session.add(
        AuditLog(
            actor_id=token_user_id(request.cookies.get(COOKIE_NAME), get_settings()),
            method=request.method,
            path=request.url.path[:255],
            status_code=route_status or response.status_code or 200,
        )
    )
