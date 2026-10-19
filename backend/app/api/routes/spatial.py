import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.models import SpatialLayer
from app.db.session import get_session
from app.domain import audit as audit_service
from app.domain import spatial as spatial_service
from app.domain.predictions import get_prediction_source
from app.domain.scopes import Scope, ScopeDep
from app.schemas.spatial import GeoJsonImport, SpatialCollectionOut, SpatialStatus, WktImport

router = APIRouter(tags=["spatial"])

SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]
WriterDep = Annotated[Principal, Depends(require_min_role("admin"))]

NOT_CONFIGURED = (
    "Пространственный слой не настроен: импортируйте геометрию "
    "или загрузите реестр каналов с идентификаторами объектов"
)


def _active(session: Session, settings: Settings) -> spatial_service.ActiveLayer:
    active = spatial_service.active_layer(session, get_prediction_source(settings))
    if active is None:
        raise HTTPException(status_code=404, detail=NOT_CONFIGURED)
    return active


def _stored(session: Session, layer: SpatialLayer) -> SpatialCollectionOut:
    collection = spatial_service.get_feature_collection(session)
    assert collection is not None
    return SpatialCollectionOut(
        features=collection.get("features", []),
        properties=collection.get("properties"),
        source=layer.source,
        updated_at=layer.updated_at,
    )


def _visible(features: list[dict[str, Any]], scope: Scope) -> list[dict[str, Any]]:
    if scope.unrestricted:
        return features

    def props(feature: Any) -> dict[str, Any]:
        value = feature.get("properties") if isinstance(feature, dict) else None
        return value if isinstance(value, dict) else {}

    def linked(item: dict[str, Any]) -> bool | None:
        if item.get("object_id") is not None:
            return scope.has_object(str(item["object_id"]))
        if item.get("asset_id") is not None:
            return scope.has_channel(str(item["asset_id"]))
        return None

    groups = {props(f).get("group_id") for f in features if linked(props(f))}
    result = []
    for feature in features:
        item = props(feature)
        visible = linked(item)
        if visible is None and item.get("group_id") is not None:
            visible = item["group_id"] in groups
        if visible is not False:
            result.append(feature)
    return result


@router.get("/spatial/status", response_model=SpatialStatus)
def spatial_status(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> SpatialStatus:
    state = spatial_service.layer_status(session, get_prediction_source(settings))
    return SpatialStatus.model_validate(state)


@router.get("/spatial", response_model=SpatialCollectionOut)
def get_spatial(
    session: SessionDep, settings: SettingsDep, _: ReaderDep, scope: ScopeDep
) -> SpatialCollectionOut:
    active = _active(session, settings)
    return SpatialCollectionOut(
        features=_visible(active.features, scope),
        properties=active.collection.get("properties"),
        source=active.source,
        updated_at=active.updated_at,
    )


@router.get("/spatial.geojson")
def export_geojson(
    session: SessionDep, settings: SettingsDep, _: ReaderDep, scope: ScopeDep
) -> Response:
    active = _active(session, settings)
    body = {
        "type": "FeatureCollection",
        "features": _visible(active.features, scope),
        "properties": {**(active.collection.get("properties") or {}), "source": active.source},
    }
    return Response(
        content=json.dumps(body, ensure_ascii=False),
        media_type="application/geo+json",
        headers={"Content-Disposition": 'attachment; filename="vena-spatial.geojson"'},
    )


@router.get("/spatial.wkt")
def export_wkt(session: SessionDep, settings: SettingsDep, _: ReaderDep) -> Response:
    active = _active(session, settings)
    return Response(
        content=spatial_service.to_wkt_lines(active.collection),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="vena-spatial.wkt"'},
    )


@router.put("/spatial", response_model=SpatialCollectionOut, status_code=status.HTTP_200_OK)
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
    return _stored(session, layer)


@router.put("/spatial/wkt", response_model=SpatialCollectionOut)
def put_spatial_wkt(
    body: WktImport,
    session: SessionDep,
    principal: WriterDep,
) -> SpatialCollectionOut:
    try:
        layer = spatial_service.put_wkt(
            session, [item.model_dump(exclude_none=True) for item in body.features]
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
        detail=f"features={len(body.features)}",
    )
    return _stored(session, layer)


@router.delete("/spatial", response_model=SpatialStatus)
def reset_spatial(
    session: SessionDep, settings: SettingsDep, principal: WriterDep
) -> SpatialStatus:
    layer = spatial_service.get_layer(session)
    if layer is not None:
        session.delete(layer)
        session.flush()
    audit_service.record(
        session,
        actor=principal.subject,
        role=principal.role,
        action="spatial.reset",
        resource_type="spatial_layer",
        resource_id="default",
    )
    state = spatial_service.layer_status(session, get_prediction_source(settings))
    return SpatialStatus.model_validate(state)


@router.post("/spatial/demo", response_model=SpatialCollectionOut)
def reset_demo_spatial(
    session: SessionDep,
    principal: WriterDep,
    settings: SettingsDep,
) -> SpatialCollectionOut:
    if settings.environment == "production" and not settings.seed_demo:
        raise HTTPException(409, "На боевом сервере загрузите реальные координаты объектов")
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
    return _stored(session, layer)
