from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import User
from app.db.session import get_session

COOKIE_NAME = "vena_session"
_passwords = PasswordHasher()


def hash_password(password: str) -> str:
    return _passwords.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _passwords.verify(password_hash, password)
    except VerificationError:
        return False


def create_token(user: User, settings: Settings) -> str:
    now = datetime.now(tz=UTC)
    return jwt.encode(
        {
            "sub": user.id,
            "role": user.role,
            "iat": now,
            "exp": now + timedelta(hours=8),
            "iss": "vena-api",
            "aud": "vena-web",
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def token_user_id(token: str | None, settings: Settings) -> str | None:
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="vena-api",
            audience="vena-web",
        )
    except jwt.InvalidTokenError:
        return None
    user_id = claims.get("sub")
    return user_id if isinstance(user_id, str) else None


def require_user(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            issuer="vena-api",
            audience="vena-web",
        )
    except jwt.InvalidTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from error
    user = session.get(User, claims["sub"])
    if user is None or not user.is_active or user.role != claims.get("role"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return user


def require_dispatcher(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != "dispatcher":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Dispatcher role required"
        )
    return user


def require_operator(user: Annotated[User, Depends(require_user)]) -> User:
    if user.role != "operator":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Operator role required")
    return user
