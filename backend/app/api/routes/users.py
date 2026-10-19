from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AfterValidator, BaseModel, EmailStr, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import PASSWORDS, Principal, require_min_role
from app.db.models import AuthSession, User
from app.db.session import get_session
from app.domain import audit
from app.domain import scopes as scope_service
from app.domain.hierarchy import Hierarchy
from app.domain.hierarchy import load as load_hierarchy

router = APIRouter(prefix="/users", tags=["users"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Admin = Annotated[Principal, Depends(require_min_role("admin"))]
Role = Literal["viewer", "dispatcher", "admin"]


def checked_scopes(value: list[str]) -> list[str]:
    scopes = scope_service.normalize(value)
    if not scopes:
        raise ValueError("Укажите хотя бы одну область видимости")
    return scopes


Scopes = Annotated[list[str], Field(min_length=1, max_length=200), AfterValidator(checked_scopes)]


class CreateUser(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)
    role: Role = "viewer"
    scopes: Scopes = ["all"]


class UpdateUser(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    scopes: Scopes | None = None


class ResetPassword(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


def user_dict(user: User, hierarchy: Hierarchy) -> dict:
    keys = ["id", "username", "email", "role", "is_active", "auth_provider", "created_at", "scopes"]
    return {
        **{key: getattr(user, key) for key in keys},
        "scope_label": scope_service.label(user.scopes, hierarchy, user.role),
    }


def lock_users(db: Session):
    db.execute(text("SELECT pg_advisory_xact_lock(78204102)"))


@router.get("")
def list_users(
    db: DB,
    settings: Config,
    _: Admin,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> dict:
    hierarchy = load_hierarchy(settings)
    return {
        "total": db.scalar(select(func.count()).select_from(User)),
        "items": [
            user_dict(user, hierarchy)
            for user in db.scalars(select(User).order_by(User.username).offset(offset).limit(limit))
        ],
    }


@router.post("", status_code=201)
def create_user(body: CreateUser, db: DB, settings: Config, actor: Admin) -> dict:
    lock_users(db)
    user = User(
        id=uuid4().hex,
        username=body.username.lower(),
        email=str(body.email).lower(),
        password_hash=PASSWORDS.hash(body.password),
        role=body.role,
        is_active=True,
        auth_provider="local",
        scopes=body.scopes,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        raise HTTPException(409, "Логин или email уже занят") from None
    audit.record(
        db,
        actor=actor.subject,
        role=actor.role,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        detail=f"role={user.role}, scopes={','.join(user.scopes)}",
    )
    return user_dict(user, load_hierarchy(settings))


@router.patch("/{user_id}")
def update_user(user_id: str, body: UpdateUser, db: DB, settings: Config, actor: Admin) -> dict:
    lock_users(db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.auth_provider == "ldap" and body.role is not None:
        raise HTTPException(400, "Роль корпоративного пользователя задаётся группами LDAP/AD")
    if user.auth_provider == "ldap" and body.scopes is not None:
        raise HTTPException(400, "Область корпоративного пользователя задаётся группами LDAP/AD")
    if user.id == actor.user_id and (body.is_active is False or body.role not in (None, "admin")):
        raise HTTPException(409, "Нельзя заблокировать себя или понизить собственную роль")
    if (
        user.is_active
        and user.role == "admin"
        and (body.is_active is False or body.role not in (None, "admin"))
    ):
        count = db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "admin", User.is_active.is_(True))
        )
        if (count or 0) <= 1:
            raise HTTPException(409, "Нельзя отключить последнего администратора")
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(user, key, value)
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
    audit.record(
        db,
        actor=actor.subject,
        role=actor.role,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        detail=f"role={user.role}, active={user.is_active}, scopes={','.join(user.scopes)}",
    )
    return user_dict(user, load_hierarchy(settings))


@router.post("/{user_id}/password")
def reset_password(user_id: str, body: ResetPassword, db: DB, actor: Admin) -> dict:
    lock_users(db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.auth_provider != "local":
        raise HTTPException(400, "Пароль меняется в корпоративном каталоге")
    user.password_hash = PASSWORDS.hash(body.password)
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=True))
    audit.record(
        db,
        actor=actor.subject,
        role=actor.role,
        action="user.password_reset",
        resource_type="user",
        resource_id=user.id,
    )
    return {"ok": True}
