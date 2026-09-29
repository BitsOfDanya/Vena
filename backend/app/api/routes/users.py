from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import PASSWORDS, Principal, require_min_role
from app.db.models import AuthSession, User
from app.db.session import get_session
from app.domain import audit

router = APIRouter(prefix="/users", tags=["users"])
DB = Annotated[Session, Depends(get_session)]
Admin = Annotated[Principal, Depends(require_min_role("admin"))]
Role = Literal["viewer", "dispatcher", "admin"]


class CreateUser(BaseModel):
    username: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: EmailStr
    password: str = Field(min_length=10, max_length=1024)
    role: Role = "viewer"


class UpdateUser(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class ResetPassword(BaseModel):
    password: str = Field(min_length=10, max_length=1024)


def user_dict(user: User) -> dict:
    return {
        key: getattr(user, key)
        for key in ["id", "username", "email", "role", "is_active", "auth_provider", "created_at"]
    }


def lock_users(db: Session):
    db.execute(text("SELECT pg_advisory_xact_lock(78204102)"))


@router.get("")
def list_users(
    db: DB, _: Admin, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)
) -> dict:
    return {
        "total": db.scalar(select(func.count()).select_from(User)),
        "items": [
            user_dict(user)
            for user in db.scalars(select(User).order_by(User.username).offset(offset).limit(limit))
        ],
    }


@router.post("", status_code=201)
def create_user(body: CreateUser, db: DB, actor: Admin) -> dict:
    lock_users(db)
    user = User(
        id=uuid4().hex,
        username=body.username.lower(),
        email=str(body.email).lower(),
        password_hash=PASSWORDS.hash(body.password),
        role=body.role,
        is_active=True,
        auth_provider="local",
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
        detail=f"role={user.role}",
    )
    return user_dict(user)


@router.patch("/{user_id}")
def update_user(user_id: str, body: UpdateUser, db: DB, actor: Admin) -> dict:
    lock_users(db)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.auth_provider == "ldap" and body.role is not None:
        raise HTTPException(400, "Роль корпоративного пользователя задаётся группами LDAP/AD")
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
        detail=f"role={user.role}, active={user.is_active}",
    )
    return user_dict(user)


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
