from __future__ import annotations

import json
import math
from typing import Any

ORIGIN_LON = 37.635
ORIGIN_LAT = 55.748
GROUP_STEP_LON = 0.0042
GROUP_STEP_LAT = -0.0031
ASSET_SPREAD = 0.00055

TYPES = ["pump", "fan", "smoke", "power", "other"]


def _asset_id(index: int) -> str:
    if index == 0:
        return "P-0142"
    asset_type = TYPES[index % len(TYPES)]
    return f"{asset_type[0].upper()}-{index + 101:04d}"


def build_demo_feature_collection(asset_count: int = 128, group_count: int = 16) -> dict[str, Any]:
    features: list[dict[str, Any]] = []
    corridor_coords: list[list[float]] = []

    for group_index in range(group_count):
        gx = ORIGIN_LON + (group_index % 4) * GROUP_STEP_LON * 2.2
        gy = ORIGIN_LAT + (group_index // 4) * GROUP_STEP_LAT
        corridor_coords.append([round(gx, 6), round(gy, 6)])
        group_id = f"K-{group_index + 1:02d}"
        features.append(
            {
                "type": "Feature",
                "id": f"group-{group_id}",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(gx, 6), round(gy, 6)],
                },
                "properties": {
                    "kind": "collector",
                    "group_id": group_id,
                    "name": f"Коллектор К{group_index + 1}",
                    "source": "demo_spatial",
                },
            }
        )

    if len(corridor_coords) >= 2:
        features.insert(
            0,
            {
                "type": "Feature",
                "id": "corridor-main",
                "geometry": {"type": "LineString", "coordinates": corridor_coords},
                "properties": {
                    "kind": "corridor",
                    "name": "Демонстрационный коридор коллектора",
                    "source": "demo_spatial",
                },
            },
        )

    for index in range(asset_count):
        group_index = index // 8
        gx = ORIGIN_LON + (group_index % 4) * GROUP_STEP_LON * 2.2
        gy = ORIGIN_LAT + (group_index // 4) * GROUP_STEP_LAT
        angle = (index % 8) * (2 * math.pi / 8)
        lon = gx + math.cos(angle) * ASSET_SPREAD
        lat = gy + math.sin(angle) * ASSET_SPREAD * 0.7
        asset_type = TYPES[index % len(TYPES)]
        asset_id = _asset_id(index)
        features.append(
            {
                "type": "Feature",
                "id": asset_id,
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(lon, 6), round(lat, 6)],
                },
                "properties": {
                    "kind": "asset",
                    "asset_id": asset_id,
                    "group_id": f"K-{group_index + 1:02d}",
                    "asset_type": asset_type,
                    "name": f"{asset_type} {index + 1}",
                    "source": "demo_spatial",
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": "demo_spatial",
            "crs": "EPSG:4326",
            "note": "Геометрия стенда для карты; заменяется через PUT /spatial.",
        },
    }


def dumps_demo() -> str:
    return json.dumps(build_demo_feature_collection(), ensure_ascii=False)
