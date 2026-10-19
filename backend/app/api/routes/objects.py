from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal
from app.db.models import Equipment
from app.db.session import get_session
from app.domain.hierarchy import build_tree, load
from app.domain.predictions import get_prediction_source
from app.domain.scopes import ScopeDep
from app.schemas.objects import ObjectTree

router = APIRouter(prefix="/objects", tags=["objects"])


@router.get("/tree", response_model=ObjectTree)
def object_tree(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    _: Annotated[Principal, Depends(get_principal)],
    scope: ScopeDep,
) -> ObjectTree:
    channels: dict[str, str] = {}
    source = get_prediction_source(settings)
    if source.available:
        channels.update({item.asset_id: item.object_id for item in source.all() if item.object_id})
    registry = select(Equipment.asset_id, Equipment.object_id).where(Equipment.status != "retired")
    channels.update({asset_id: object_id for asset_id, object_id in session.execute(registry)})
    return build_tree(load(settings), Counter(channels.values()), scope.objects)
