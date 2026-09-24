from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import InfrastructureObject, NetworkEdge
from app.db.session import get_session

router = APIRouter(prefix="/map", tags=["map"])
SessionDep = Annotated[Session, Depends(get_session)]


class MapNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    district: str
    object_type: str
    status: str
    latitude: float
    longitude: float
    is_demo: bool


class MapEdge(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_id: str
    target_id: str
    kind: str
    is_demo: bool


class MapNetwork(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]


@router.get("/network", response_model=MapNetwork)
def network(session: SessionDep) -> MapNetwork:
    objects = session.scalars(
        select(InfrastructureObject)
        .where(
            InfrastructureObject.latitude.is_not(None),
            InfrastructureObject.longitude.is_not(None),
        )
        .order_by(InfrastructureObject.id)
    ).all()
    nodes = [MapNode.model_validate(item) for item in objects]
    ids = {node.id for node in nodes}
    edges = [
        MapEdge.model_validate(item)
        for item in session.scalars(select(NetworkEdge).order_by(NetworkEdge.id))
        if item.source_id in ids and item.target_id in ids
    ]
    return MapNetwork(nodes=nodes, edges=edges)
