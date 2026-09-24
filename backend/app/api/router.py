from fastapi import APIRouter, Depends

from app.api.routes import (
    actions,
    audit,
    auth,
    data,
    health,
    imports,
    map,
    ml,
    notifications,
    predictions,
    settings,
    system,
)
from app.core.audit import audit_mutation
from app.core.auth import require_dispatcher, require_user
from app.core.config import get_settings

api_router = APIRouter(prefix=get_settings().api_v1_prefix)
api_router.include_router(health.router)
api_router.include_router(auth.router, dependencies=[Depends(audit_mutation)])
protected_router = APIRouter(dependencies=[Depends(require_user), Depends(audit_mutation)])
protected_router.include_router(ml.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(notifications.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(actions.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(settings.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(system.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(predictions.router, dependencies=[Depends(require_dispatcher)])
protected_router.include_router(imports.router)
protected_router.include_router(data.router)
protected_router.include_router(map.router)
protected_router.include_router(audit.router)
api_router.include_router(protected_router)
