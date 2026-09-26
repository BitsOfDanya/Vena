from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import Principal, get_principal

router = APIRouter(tags=["auth"])


@router.get("/auth/me")
def auth_me(principal: Annotated[Principal, Depends(get_principal)]) -> dict[str, str]:
    return {
        "subject": principal.subject,
        "role": principal.role,
        "auth_method": principal.auth_method,
    }
