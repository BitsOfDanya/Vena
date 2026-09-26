from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import SpatialLayer
from app.domain.demo_spatial import dumps_demo

_WKT_POINT = re.compile(
    r"^\s*POINT\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)\s*$",
    re.IGNORECASE,
)


def get_layer(session: Session) -> SpatialLayer | None:
    return session.get(SpatialLayer, "default")


def get_feature_collection(session: Session) -> dict[str, Any] | None:
    layer = get_layer(session)
    if layer is None or not layer.feature_collection.strip():
        return None
    return json.loads(layer.feature_collection)


def layer_status(session: Session) -> dict[str, Any]:
    layer = get_layer(session)
    if layer is None:
        return {
            "configured": False,
            "source": None,
            "feature_count": 0,
            "asset_count": 0,
            "updated_at": None,
        }
    collection = json.loads(layer.feature_collection)
    features = collection.get("features", [])
    asset_count = sum(
        1
        for feature in features
        if isinstance(feature, dict)
        and (feature.get("properties") or {}).get("kind") == "asset"
    )
    return {
        "configured": True,
        "source": layer.source,
        "feature_count": len(features),
        "asset_count": asset_count,
        "updated_at": layer.updated_at.isoformat() if layer.updated_at else None,
    }


def ensure_demo_spatial(session: Session) -> SpatialLayer:
    layer = get_layer(session)
    if layer is not None:
        return layer
    layer = SpatialLayer(id="default", feature_collection=dumps_demo(), source="demo_spatial")
    session.add(layer)
    session.flush()
    return layer


def put_geojson(session: Session, payload: dict[str, Any], source: str = "import") -> SpatialLayer:
    if payload.get("type") != "FeatureCollection":
        raise ValueError("expected GeoJSON FeatureCollection")
    features = payload.get("features")
    if not isinstance(features, list):
        raise ValueError("FeatureCollection.features must be a list")
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("each item must be a GeoJSON Feature")
        geometry = feature.get("geometry")
        if (
            not isinstance(geometry, dict)
            or "type" not in geometry
            or "coordinates" not in geometry
        ):
            raise ValueError("each Feature must include geometry")
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


def parse_wkt_point(wkt: str) -> tuple[float, float]:
    match = _WKT_POINT.match(wkt)
    if not match:
        raise ValueError(f"unsupported WKT (expected POINT): {wkt[:80]}")
    lon, lat = float(match.group(1)), float(match.group(2))
    return lon, lat


def put_wkt_points(
    session: Session,
    points: list[dict[str, str]],
    source: str = "import_wkt",
) -> SpatialLayer:
    """Replace asset points from WKT POINT list; keep corridor from demo if present."""
    existing = get_feature_collection(session) or {"type": "FeatureCollection", "features": []}
    retained = [
        feature
        for feature in existing.get("features", [])
        if isinstance(feature, dict)
        and (feature.get("properties") or {}).get("kind") in {"corridor", "collector"}
    ]
    features = list(retained)
    for item in points:
        asset_id = item["asset_id"].strip()
        lon, lat = parse_wkt_point(item["wkt"])
        features.append(
            {
                "type": "Feature",
                "id": asset_id,
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "kind": "asset",
                    "asset_id": asset_id,
                    "source": source,
                },
            }
        )
    return put_geojson(
        session,
        {"type": "FeatureCollection", "features": features, "properties": {"source": source}},
        source=source,
    )
