from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import engine

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    service: str
    version: str
    database: Literal["ok", "unavailable"] = "ok"


@router.get(
    "",
    response_model=HealthResponse,
    summary="Check service health",
    responses={503: {"model": HealthResponse, "description": "Database unavailable"}},
)
def health_check(response: Response) -> HealthResponse:
    settings = get_settings()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return HealthResponse(
            status="degraded",
            database="unavailable",
            service=settings.app_name,
            version=settings.app_version,
        )
    return HealthResponse(service=settings.app_name, version=settings.app_version)
