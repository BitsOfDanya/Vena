import hashlib
import hmac
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import AliasChoices, BaseModel, Field
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import ldap as directory
from app.core.config import Settings, get_settings
from app.core.security import (
    COOKIE_NAME,
    DUMMY_HASH,
    PASSWORDS,
    Principal,
    check_origin,
    client_ip,
    get_principal,
    issue_token,
    signing_key,
)
from app.db.models import AuthSession, LoginBucket, User
from app.db.session import get_session
from app.domain import audit
from app.domain import scopes as scope_service
from app.domain.hierarchy import load as load_hierarchy

router = APIRouter(prefix="/auth", tags=["auth"])
SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[Session, Depends(get_session)]
PrincipalDep = Annotated[Principal, Depends(get_principal)]


class AuthMe(BaseModel):
    subject: str
    role: str
    auth_method: str
    email: str | None = None
    scopes: list[str] = ["all"]
    scope_label: str = "Все объекты"


class LoginRequest(BaseModel):
    login: str = Field(
        min_length=1, max_length=254, validation_alias=AliasChoices("email", "login")
    )
    password: str = Field(min_length=1, max_length=1024)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthMe


class PasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=1024)


def throttle(session: Session, settings: Settings, identity: str, ip: str) -> None:
    now = datetime.now(UTC)
    session.execute(delete(LoginBucket).where(LoginBucket.expires_at < now - timedelta(hours=1)))
    for name, limit in [(f"ip:{ip}", 100), (f"login:{identity}", settings.auth_login_limit)]:
        key = hmac.new(signing_key(settings).encode(), name.encode(), hashlib.sha256).hexdigest()
        session.execute(
            insert(LoginBucket)
            .values(
                id=key,
                attempts=0,
                expires_at=now + timedelta(seconds=settings.auth_login_window_seconds),
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        bucket = session.execute(
            select(LoginBucket).where(LoginBucket.id == key).with_for_update()
        ).scalar_one()
        if bucket.expires_at <= now:
            bucket.attempts = 0
            bucket.expires_at = now + timedelta(seconds=settings.auth_login_window_seconds)
        if bucket.attempts >= limit:
            retry = max(1, int((bucket.expires_at - now).total_seconds()))
            session.commit()
            raise HTTPException(
                429, "Too many attempts. Try again later.", headers={"Retry-After": str(retry)}
            )
        bucket.attempts += 1
        session.flush()


def login_failed(
    session: Session, login: str, reason: str, ip: str | None, user: User | None = None
) -> HTTPException:
    audit.record(
        session,
        actor=login,
        role=user.role if user else "",
        action="auth.login_failed",
        resource_type="user" if user else "",
        resource_id=user.id if user else "",
        detail=f"reason={reason}",
        ip=ip,
    )
    session.commit()
    return HTTPException(
        401, "Неверный email, логин или пароль", headers={"WWW-Authenticate": "Bearer"}
    )


def describe(
    settings: Settings,
    subject: str,
    role: str,
    method: str,
    email: str | None,
    scopes: Sequence[str],
) -> AuthMe:
    return AuthMe(
        subject=subject,
        role=role,
        auth_method=method,
        email=email,
        scopes=list(scopes),
        scope_label=scope_service.label(scopes, load_hierarchy(settings), role),
    )


def set_session_cookie(response: Response, token: str, ttl: int, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=ttl,
        httponly=True,
        secure=settings.public_url.startswith("https://"),
        samesite="lax",
        path="/api/v1",
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/status")
def auth_status(settings: SettingsDep) -> dict:
    return {
        "auth_enabled": settings.auth_enabled,
        "methods": (["password"] + (["ldap"] if settings.ldap_configured else []))
        if settings.auth_enabled
        else [],
        "configured": len(settings.jwt_secret.encode()) >= 32,
        "ldap_available": settings.ldap_configured,
    }


@router.get("/me", response_model=AuthMe)
def auth_me(principal: PrincipalDep, response: Response, settings: SettingsDep) -> AuthMe:
    response.headers["Cache-Control"] = "no-store"
    return describe(
        settings,
        principal.subject,
        principal.role,
        principal.auth_method,
        principal.email,
        principal.scopes,
    )


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> TokenResponse:
    signing_key(settings)
    check_origin(request, settings)
    identity = body.login.strip().lower()
    ip = client_ip(request, settings)
    throttle(session, settings, identity, ip or "unknown")
    user = session.scalar(
        select(User).where(or_(User.email == identity, User.username == identity)).with_for_update()
    )
    valid = PASSWORDS.verify(
        body.password, user.password_hash if user and user.auth_provider == "local" else DUMMY_HASH
    )
    if not user:
        raise login_failed(session, identity, "unknown_login", ip)
    if user.auth_provider != "local":
        raise login_failed(session, identity, "directory_account", ip, user)
    if not valid:
        raise login_failed(session, identity, "password", ip, user)
    if not user.is_active:
        raise login_failed(session, identity, "disabled", ip, user)
    session.execute(delete(AuthSession).where(AuthSession.expires_at < datetime.now(UTC)))
    token, ttl = issue_token(user, session, settings)
    audit.record(
        session,
        actor=user.username,
        role=user.role,
        action="auth.login",
        resource_type="user",
        resource_id=user.id,
        detail="scopes=" + ",".join(user.scopes),
        ip=ip,
    )
    session.commit()
    set_session_cookie(response, token, ttl, settings)
    return TokenResponse(
        access_token=token,
        expires_in=ttl,
        user=describe(settings, user.username, user.role, "jwt", user.email, user.scopes),
    )


@router.post("/ldap", response_model=TokenResponse)
def ldap_login(
    body: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
) -> TokenResponse:
    signing_key(settings)
    check_origin(request, settings)
    login = body.login.strip().lower()
    ip = client_ip(request, settings)
    throttle(session, settings, "ldap:" + login, ip or "unknown")
    session.commit()
    try:
        identity = directory.authenticate(settings, body.login, body.password)
    except directory.DirectoryDenied:
        raise login_failed(session, login, "ldap_denied", ip) from None
    except directory.DirectoryUnavailable:
        raise HTTPException(503, "Корпоративный каталог недоступен или не настроен") from None
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": identity.directory_id},
    )
    user = session.scalar(select(User).where(User.directory_id == identity.directory_id))
    if user and (not user.is_active or user.auth_provider != "ldap"):
        raise login_failed(session, login, "ldap_disabled", ip, user)
    if user is None:
        user = User(
            id=uuid4().hex,
            username=identity.username,
            email=identity.email,
            password_hash="!ldap",
            role=identity.role,
            auth_provider="ldap",
            directory_id=identity.directory_id,
        )
        session.add(user)
    user.username, user.email, user.role = identity.username, identity.email, identity.role
    user.scopes = list(identity.scopes)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            409, "Учётная запись каталога конфликтует с существующей записью"
        ) from None
    token, ttl = issue_token(user, session, settings)
    audit.record(
        session,
        actor=user.username,
        role=user.role,
        action="auth.ldap_login",
        resource_type="user",
        resource_id=user.id,
        detail="scopes=" + ",".join(user.scopes),
        ip=ip,
    )
    session.commit()
    set_session_cookie(response, token, ttl, settings)
    return TokenResponse(
        access_token=token,
        expires_in=ttl,
        user=describe(settings, user.username, user.role, "ldap", user.email, user.scopes),
    )


@router.post("/logout")
def logout(principal: PrincipalDep, session: SessionDep, response: Response) -> dict:
    if principal.session_id:
        session.execute(
            update(AuthSession).where(AuthSession.id == principal.session_id).values(revoked=True)
        )
        audit.record(
            session,
            actor=principal.subject,
            role=principal.role,
            action="auth.logout",
            resource_type="user",
            resource_id=principal.user_id or "",
        )
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}


@router.post("/password")
def change_password(
    body: PasswordRequest,
    principal: PrincipalDep,
    session: SessionDep,
    settings: SettingsDep,
    response: Response,
) -> dict:
    user = session.get(User, principal.user_id) if principal.user_id else None
    if not user or user.auth_provider != "local":
        raise HTTPException(400, "Измените пароль в корпоративном каталоге")
    throttle(session, settings, f"password:{user.id}", f"user:{user.id}")
    user = session.execute(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).scalar_one()
    if not PASSWORDS.verify(body.current_password, user.password_hash):
        session.commit()
        raise HTTPException(400, "Текущий пароль неверен")
    user.password_hash = PASSWORDS.hash(body.new_password)
    session.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
    audit.record(
        session,
        actor=user.username,
        role=user.role,
        action="auth.password_change",
        resource_type="user",
        resource_id=user.id,
    )
    session.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
