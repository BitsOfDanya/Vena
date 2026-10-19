from fastapi import APIRouter

from app.api.routes import (
    actions,
    analytics,
    audit,
    auth,
    equipment,
    health,
    incidents,
    journal,
    ml,
    notifications,
    objects,
    predictions,
    replay,
    settings,
    smvu,
    spatial,
    system,
    thresholds,
    users,
)
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_v1_prefix)
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(ml.router)
api_router.include_router(thresholds.router)
api_router.include_router(notifications.router)
api_router.include_router(actions.router)
api_router.include_router(settings.router)
api_router.include_router(system.router)
api_router.include_router(predictions.router)
api_router.include_router(journal.router)
api_router.include_router(analytics.router)
api_router.include_router(audit.router)
api_router.include_router(spatial.router)
api_router.include_router(smvu.router)
api_router.include_router(replay.router)

api_router.include_router(equipment.router)
api_router.include_router(users.router)
api_router.include_router(objects.router)
api_router.include_router(incidents.router)
