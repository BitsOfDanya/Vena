from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.core.security import Principal, auth_status_payload, get_principal, resolve_api_key

router = APIRouter(tags=["auth"])


class AuthStatus(BaseModel):
    auth_enabled: bool
    methods: list[str]
    keys_configured: bool
    ldap_available: bool = False


class AuthMe(BaseModel):
    subject: str
    role: str
    auth_method: str


class AuthLoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=200)


@router.get("/auth/status", response_model=AuthStatus)
def auth_status(settings: Annotated[Settings, Depends(get_settings)]) -> AuthStatus:
    """Public: whether the UI must collect an API key."""
    return AuthStatus.model_validate(auth_status_payload(settings))


@router.get("/auth/me", response_model=AuthMe)
def auth_me(principal: Annotated[Principal, Depends(get_principal)]) -> AuthMe:
    return AuthMe(
        subject=principal.subject,
        role=principal.role,
        auth_method=principal.auth_method,
    )


@router.post("/auth/login", response_model=AuthMe)
def auth_login(
    body: AuthLoginRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthMe:
    """Validate an API key without requiring prior authentication."""
    if not settings.auth_enabled:
        return AuthMe(subject="Duty engineer", role="admin", auth_method="disabled")
    principal = resolve_api_key(settings, body.api_key.strip())
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid api key",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return AuthMe(
        subject=principal.subject,
        role=principal.role,
        auth_method=principal.auth_method,
    )


@router.post("/auth/logout", response_model=dict[str, bool])
def auth_logout() -> dict[str, bool]:
    """Stateless API-key auth: client clears the stored key."""
    return {"ok": True}
