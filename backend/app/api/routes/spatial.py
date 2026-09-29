from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import Principal, get_principal, require_min_role
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import spatial as spatial_service
from app.schemas.spatial import GeoJsonImport, SpatialCollectionOut, SpatialStatus, WktImport

router = APIRouter(prefix="/spatial", tags=["spatial"])

SessionDep = Annotated[Session, Depends(get_session)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
WriterDep = Annotated[Principal, Depends(require_min_role("admin"))]


@router.get("/status", response_model=SpatialStatus)
def spatial_status(session: SessionDep, _: ReaderDep) -> SpatialStatus:
    return SpatialStatus.model_validate(spatial_service.layer_status(session))


@router.get("", response_model=SpatialCollectionOut)
def get_spatial(session: SessionDep, _: ReaderDep) -> SpatialCollectionOut:
    layer = spatial_service.get_layer(session)
    if layer is None:
        raise HTTPException(status_code=404, detail="Пространственный слой не настроен")
    collection = spatial_service.get_feature_collection(session)
    assert collection is not None
    return SpatialCollectionOut(
        features=collection.get("features", []),
        properties=collection.get("properties"),
        source=layer.source,
        updated_at=layer.updated_at,
    )


@router.put("", response_model=SpatialCollectionOut, status_code=status.HTTP_200_OK)
def put_spatial(
    body: GeoJsonImport,
    session: SessionDep,
    principal: WriterDep,
) -> SpatialCollectionOut:
    try:
        layer = spatial_service.put_geojson(
            session, body.model_dump(exclude_none=True), source="import"
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="spatial.import_geojson",
        resource_type="spatial_layer",
        resource_id="default",
        detail=f"features={len(body.features)}",
    )
    collection = spatial_service.get_feature_collection(session)
    assert collection is not None
    return SpatialCollectionOut(
        features=collection.get("features", []),
        properties=collection.get("properties"),
        source=layer.source,
        updated_at=layer.updated_at,
    )


@router.put("/wkt", response_model=SpatialCollectionOut)
def put_spatial_wkt(
    body: WktImport,
    session: SessionDep,
    principal: WriterDep,
) -> SpatialCollectionOut:
    try:
        layer = spatial_service.put_wkt_points(
            session,
            [{"asset_id": point.asset_id, "wkt": point.wkt} for point in body.points],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="spatial.import_wkt",
        resource_type="spatial_layer",
        resource_id="default",
        detail=f"points={len(body.points)}",
    )
    collection = spatial_service.get_feature_collection(session)
    assert collection is not None
    return SpatialCollectionOut(
        features=collection.get("features", []),
        properties=collection.get("properties"),
        source=layer.source,
        updated_at=layer.updated_at,
    )


@router.post("/demo", response_model=SpatialCollectionOut)
def reset_demo_spatial(session: SessionDep, principal: WriterDep) -> SpatialCollectionOut:
    existing = spatial_service.get_layer(session)
    if existing is not None:
        session.delete(existing)
        session.flush()
    layer = spatial_service.ensure_demo_spatial(session)
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="spatial.reset_demo",
        resource_type="spatial_layer",
        resource_id="default",
    )
    collection = spatial_service.get_feature_collection(session)
    assert collection is not None
    return SpatialCollectionOut(
        features=collection.get("features", []),
        properties=collection.get("properties"),
        source=layer.source,
        updated_at=layer.updated_at,
    )
