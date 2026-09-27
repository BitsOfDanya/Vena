from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings

Role = Literal["admin", "dispatcher", "viewer"]

ROLE_RANK: dict[Role, int] = {"viewer": 1, "dispatcher": 2, "admin": 3}


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    auth_method: str = "disabled"


@dataclass(frozen=True)
class ApiKeyRecord:
    role: Role
    subject: str


def _parse_api_keys(raw: str) -> dict[str, ApiKeyRecord]:
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    result: dict[str, ApiKeyRecord] = {}
    for key, value in payload.items():
        token = str(key).strip()
        if not token:
            continue
        role: str | None = None
        subject: str | None = None
        if isinstance(value, str):
            role = value
            subject = f"api-key:{value}"
        elif isinstance(value, dict):
            maybe_role = value.get("role")
            if isinstance(maybe_role, str):
                role = maybe_role
            maybe_subject = value.get("subject") or value.get("name")
            if isinstance(maybe_subject, str) and maybe_subject.strip():
                subject = maybe_subject.strip()
        if role in ROLE_RANK:
            result[token] = ApiKeyRecord(
                role=role,  # type: ignore[arg-type]
                subject=subject or f"api-key:{role}",
            )
    return result


def resolve_api_key(settings: Settings, token: str | None) -> Principal | None:
    if not token:
        return None
    keys = _parse_api_keys(settings.api_keys_json)
    record = keys.get(token)
    if record is None:
        return None
    return Principal(subject=record.subject, role=record.role, auth_method="api_key")


def extract_bearer_or_api_key(
    x_api_key: str | None,
    authorization: str | None,
) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def get_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> Principal:
    if not settings.auth_enabled:
        return Principal(subject="Duty engineer", role="admin", auth_method="disabled")

    keys = _parse_api_keys(settings.api_keys_json)
    if not keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication enabled but VENA_API_KEYS_JSON is empty or invalid",
        )

    token = extract_bearer_or_api_key(x_api_key, authorization)
    principal = resolve_api_key(settings, token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return principal


def require_min_role(minimum: Role):
    threshold = ROLE_RANK[minimum]

    def dependency(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
        if ROLE_RANK[principal.role] < threshold:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")
        return principal

    return dependency


def auth_status_payload(settings: Settings) -> dict[str, Any]:
    keys = _parse_api_keys(settings.api_keys_json) if settings.auth_enabled else {}
    return {
        "auth_enabled": settings.auth_enabled,
        "methods": ["api_key"] if settings.auth_enabled else [],
        "keys_configured": bool(keys),
        "ldap_available": False,
    }
