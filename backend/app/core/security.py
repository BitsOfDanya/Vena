from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings

Role = Literal["admin", "dispatcher", "viewer"]

ROLE_RANK: dict[Role, int] = {"viewer": 1, "dispatcher": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    auth_method: str = "disabled"


def _parse_api_keys(raw: str) -> dict[str, Role]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    result: dict[str, Role] = {}
    for key, role in payload.items():
        if isinstance(role, str) and role in ROLE_RANK:
            result[str(key)] = role  # type: ignore[assignment]
    return result


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not settings.auth_enabled:
        return Principal(subject="Duty engineer", role="admin", auth_method="disabled")

    keys = _parse_api_keys(settings.api_keys_json)
    token = x_api_key
    if token is None and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token or token not in keys:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "API-Key"},
        )
    role = keys[token]
    return Principal(subject=f"api-key:{role}", role=role, auth_method="api_key")


def require_min_role(minimum: Role):
    threshold = ROLE_RANK[minimum]

    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if ROLE_RANK[principal.role] < threshold:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return principal

    return dependency
