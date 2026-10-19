from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SpatialLayer
from app.domain import schematic, wkt
from app.domain.demo_spatial import dumps_demo
from app.domain.predictions import PredictionSource

DEMO = "demo_spatial"
LABELS = {
    "import": "Импортированный GeoJSON",
    "import_wkt": "Импортированный WKT",
    DEMO: "Демонстрационный слой",
    schematic.SOURCE: schematic.LABEL,
}


@dataclass
class ActiveLayer:
    collection: dict[str, Any]
    source: str
    updated_at: datetime | None

    @property
    def features(self) -> list[dict[str, Any]]:
        return [item for item in self.collection.get("features", []) if isinstance(item, dict)]


def get_layer(session: Session) -> SpatialLayer | None:
    return session.get(SpatialLayer, "default")


def get_feature_collection(session: Session) -> dict[str, Any] | None:
    layer = get_layer(session)
    if layer is None or not layer.feature_collection.strip():
        return None
    return json.loads(layer.feature_collection)


def active_layer(session: Session, source: PredictionSource) -> ActiveLayer | None:
    layer = get_layer(session)
    stored = get_feature_collection(session)
    if layer is not None and stored is not None and layer.source != DEMO:
        return ActiveLayer(stored, layer.source, layer.updated_at)
    generated = schematic.generate(session, source)
    if generated is not None:
        return ActiveLayer(generated, schematic.SOURCE, None)
    if layer is not None and stored is not None:
        return ActiveLayer(stored, layer.source, layer.updated_at)
    return None


def _kind(feature: dict[str, Any]) -> str:
    return str((feature.get("properties") or {}).get("kind") or "")


def layer_status(session: Session, source: PredictionSource) -> dict[str, Any]:
    active = active_layer(session, source)
    layer = get_layer(session)
    imported = layer is not None and layer.source != DEMO
    if active is None:
        return {
            "configured": False,
            "source": None,
            "label": None,
            "imported": False,
            "generated": False,
            "feature_count": 0,
            "asset_count": 0,
            "collector_count": 0,
            "gallery_count": 0,
            "object_count": 0,
            "updated_at": None,
            "detail": "Нет импортированной геометрии и нет каналов в реестре или снимке прогнозов",
        }
    kinds = [_kind(feature) for feature in active.features]
    objects = {
        str((feature.get("properties") or {}).get("object_id"))
        for feature in active.features
        if (feature.get("properties") or {}).get("object_id")
    }
    generated = active.source == schematic.SOURCE
    return {
        "configured": True,
        "source": active.source,
        "label": LABELS.get(active.source, active.source),
        "imported": imported,
        "generated": generated,
        "feature_count": len(kinds),
        "asset_count": kinds.count("asset"),
        "collector_count": kinds.count("collector"),
        "gallery_count": kinds.count("gallery"),
        "object_count": len(objects),
        "updated_at": active.updated_at,
        "detail": schematic.NOTE if generated else None,
    }


def ensure_demo_spatial(session: Session) -> SpatialLayer:
    layer = get_layer(session)
    if layer is not None:
        return layer
    layer = SpatialLayer(id="default", feature_collection=dumps_demo(), source=DEMO)
    session.add(layer)
    session.flush()
    return layer


def put_geojson(session: Session, payload: dict[str, Any], source: str = "import") -> SpatialLayer:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("Ожидается GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("Поле features должно быть списком")
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Каждый элемент features должен быть объектом GeoJSON Feature")
        geometry = feature.get("geometry")
        if (
            not isinstance(geometry, dict)
            or "type" not in geometry
            or ("coordinates" not in geometry and "geometries" not in geometry)
        ):
            raise ValueError("У каждого объекта должна быть геометрия с координатами")
    body = json.dumps(payload, ensure_ascii=False)
    layer = get_layer(session)
    if layer is None:
        layer = SpatialLayer(id="default", feature_collection=body, source=source)
        session.add(layer)
    else:
        layer.feature_collection = body
        layer.source = source
    session.flush()
    return layer


def wkt_feature(item: dict[str, Any], source: str) -> dict[str, Any]:
    identifier = str(item["id"]).strip()
    try:
        geometry = wkt.parse(item["wkt"])
    except wkt.WktError as error:
        raise ValueError(f"{identifier}: {error}") from error
    kind = item.get("kind") or (
        "asset" if geometry["type"] in {"Point", "MultiPoint"} else "collector"
    )
    properties: dict[str, Any] = {"kind": kind, "source": source}
    if kind == "asset":
        properties["asset_id"] = identifier
    for key in ("object_id", "name"):
        if item.get(key):
            properties[key] = item[key]
    if item.get("object_id"):
        properties["group_id"] = item["object_id"]
    return {"type": "Feature", "id": identifier, "geometry": geometry, "properties": properties}


def put_wkt(
    session: Session,
    items: list[dict[str, Any]],
    source: str = "import_wkt",
) -> SpatialLayer:
    imported = [wkt_feature(item, source) for item in items]
    kinds = {_kind(feature) for feature in imported}
    existing = get_feature_collection(session) or {"type": "FeatureCollection", "features": []}
    retained = [
        feature
        for feature in existing.get("features", [])
        if isinstance(feature, dict) and _kind(feature) and _kind(feature) not in kinds
    ]
    return put_geojson(
        session,
        {
            "type": "FeatureCollection",
            "features": [*retained, *imported],
            "properties": {"source": source},
        },
        source=source,
    )


def to_wkt_lines(collection: dict[str, Any]) -> str:
    lines = []
    for index, feature in enumerate(collection.get("features", []), start=1):
        if not isinstance(feature, dict) or not isinstance(feature.get("geometry"), dict):
            continue
        properties = feature.get("properties") or {}
        identifier = feature.get("id", properties.get("asset_id", index))
        clean = str(identifier).replace(";", ",").replace("\n", " ").replace("\r", " ")
        try:
            lines.append(f"{clean};{wkt.dumps(feature['geometry'])}")
        except (wkt.WktError, TypeError, IndexError, KeyError):
            continue
    return "\n".join(lines) + ("\n" if lines else "")
