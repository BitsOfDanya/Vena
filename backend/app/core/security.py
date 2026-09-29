from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal, cast
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import AuthSession, User
from app.db.session import get_session

Role = Literal["admin", "dispatcher", "viewer"]
ROLE_RANK: dict[Role, int] = {"viewer": 1, "dispatcher": 2, "admin": 3}
COOKIE_NAME = "vena_session"
PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash("dummy-account-password-never-used")


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    auth_method: str = "disabled"
    user_id: str | None = None
    email: str | None = None
    session_id: str | None = None


def signing_key(settings: Settings) -> str:
    if len(settings.jwt_secret.encode()) < 32:
        raise HTTPException(503, "Авторизация не настроена")
    return settings.jwt_secret


def check_origin(request: Request, settings: Settings, *, required: bool = False) -> None:
    origin = request.headers.get("origin")
    allowed = {
        settings.public_url.rstrip("/"),
        *(str(o).rstrip("/") for o in settings.cors_origins),
    }
    if (required and not origin) or (origin and origin not in allowed):
        raise HTTPException(403, "Источник запроса не разрешён")


def issue_token(user: User, session: Session, settings: Settings) -> tuple[str, int]:
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=settings.jwt_ttl_minutes)
    token_id = uuid4().hex
    token = jwt.encode(
        {
            "sub": user.id,
            "jti": token_id,
            "iat": now,
            "nbf": now,
            "exp": expires,
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
            "type": "access",
        },
        signing_key(settings),
        algorithm="HS256",
    )
    session.add(AuthSession(id=token_id, user_id=user.id, expires_at=expires))
    return token, settings.jwt_ttl_minutes * 60


def unauthorized() -> HTTPException:
    return HTTPException(401, "Требуется вход в систему", headers={"WWW-Authenticate": "Bearer"})


def get_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> Principal:
    if not settings.auth_enabled:
        return Principal(subject="Duty engineer", role="admin")
    key = signing_key(settings)
    authorization = request.headers.get("authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise unauthorized()
    else:
        token = request.cookies.get(COOKIE_NAME, "")
        if token and request.method not in {"GET", "HEAD", "OPTIONS"}:
            check_origin(request, settings, required=True)
    if not token:
        raise unauthorized()
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "jti", "exp", "iat", "nbf", "iss", "aud", "type"]},
        )
        if payload["type"] != "access":
            raise unauthorized()
    except jwt.InvalidTokenError:
        raise unauthorized() from None
    auth_session = session.get(AuthSession, payload["jti"])
    if (
        not auth_session
        or auth_session.revoked
        or auth_session.user_id != payload["sub"]
        or auth_session.expires_at <= datetime.now(UTC)
    ):
        raise unauthorized()
    user = session.get(User, payload["sub"])
    if not user or not user.is_active or user.role not in ROLE_RANK:
        raise unauthorized()
    return Principal(
        subject=user.username,
        role=cast(Role, user.role),
        auth_method="ldap" if user.auth_provider == "ldap" else "jwt",
        user_id=user.id,
        email=user.email,
        session_id=auth_session.id,
    )


def require_min_role(minimum: Role):
    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if ROLE_RANK[principal.role] < ROLE_RANK[minimum]:
            raise HTTPException(403, "Недостаточно прав")
        return principal

    return dependency
