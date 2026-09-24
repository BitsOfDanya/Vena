from fastapi import APIRouter

from app.api.routes import actions, health, ml, notifications, predictions, settings, system
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_v1_prefix)
api_router.include_router(health.router)
api_router.include_router(ml.router)
api_router.include_router(notifications.router)
api_router.include_router(actions.router)
api_router.include_router(settings.router)
api_router.include_router(system.router)
api_router.include_router(predictions.router)
