from fastapi import APIRouter

from app.api.routes import health
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_v1_prefix)
api_router.include_router(health.router)
