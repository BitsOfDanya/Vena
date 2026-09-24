from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import COOKIE_NAME, create_token, hash_password, require_user, verify_password
from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
CurrentUser = Annotated[User, Depends(require_user)]


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    role: Literal["operator", "dispatcher"]
    invite_code: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: Literal["operator", "dispatcher"]


def _out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=cast(Literal["operator", "dispatcher"], user.role),
    )


def _set_cookie(response: Response, user: User, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_token(user, settings),
        max_age=8 * 60 * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    payload: RegisterRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    email = str(payload.email).lower()
    if session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Account already exists")
    if payload.role == "dispatcher":
        first_account = session.scalar(select(func.count()).select_from(User)) == 0
        invite_required = bool(settings.dispatcher_invite_code) and not first_account
        if invite_required and payload.invite_code != settings.dispatcher_invite_code:
            raise HTTPException(status_code=403, detail="Dispatcher invitation required")
    user = User(
        id=uuid4().hex,
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    session.add(user)
    session.flush()
    _set_cookie(response, user, settings)
    return _out(user)


@router.post("/login", response_model=UserOut)
def login(
    payload: LoginRequest, response: Response, session: SessionDep, settings: SettingsDep
) -> UserOut:
    user = session.scalar(select(User).where(User.email == str(payload.email).lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _set_cookie(response, user, settings)
    return _out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _out(user)
