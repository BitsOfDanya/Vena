import json
import math
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.db.models import Equipment
from app.db.session import SessionLocal
from app.domain import schematic, wkt
from app.domain.predictions import reset_prediction_source
from tests.test_predictions import row, write_snapshot

BBOX = (37.35, 55.57, 37.85, 55.92)


@pytest.fixture()
def ml_dir(tmp_path: Path):
    settings = get_settings()
    original = settings.ml_dir
    settings.ml_dir = tmp_path
    reset_prediction_source()
    yield tmp_path
    settings.ml_dir = original
    reset_prediction_source()


def channel(channel_id: str, name: str, object_id: int = 3360) -> dict:
    return {
        **row(channel_id, 0.2, "low"),
        "name": name,
        "object_id": object_id,
        "tag": "360-1.1.3.2.",
    }


def seed_sources(ml_dir: Path) -> None:
    write_snapshot(
        ml_dir,
        datetime.now(tz=UTC),
        [
            channel("a1", "Н1 ПК47"),
            channel("a2", "Н2 ПК57"),
            channel("a3", "Н1 ПК48 Г1 ПК5"),
            channel("a4", "Н2 ПК48 Г1 ПК12"),
            channel("a5", "ДД Г2 ПК0+5"),
            channel("a6", "Насос дренажный"),
        ],
    )
    with SessionLocal.begin() as session:
        for asset_id, name, status in (
            ("r1", "Дым ПК10", "active"),
            ("r2", "Дым ПК30", "active"),
            ("r3", "Дым ПК40", "retired"),
        ):
            session.add(
                Equipment(
                    asset_id=asset_id,
                    external_id=asset_id,
                    source="test",
                    name=name,
                    object_id="5332",
                    tag="847-1.1.49.58.",
                    status=status,
                )
            )


def meters(a: list[float], b: list[float]) -> float:
    lat = math.radians((a[1] + b[1]) / 2)
    dx = (a[0] - b[0]) * 111_320 * math.cos(lat)
    dy = (a[1] - b[1]) * 111_320
    return math.hypot(dx, dy)


def coordinates(geometry: dict) -> list[list[float]]:
    if geometry["type"] == "Point":
        return [geometry["coordinates"]]
    return [point for line in geometry["coordinates"] for point in line]


def test_generated_layer_is_built_from_registry_and_snapshot(
    client: TestClient, auth_users, ml_dir: Path, monkeypatch
) -> None:
    seed_sources(ml_dir)
    headers = auth_users["viewer"]

    state = client.get("/api/v1/spatial/status", headers=headers).json()
    body = client.get("/api/v1/spatial", headers=headers).json()

    assert state["configured"] is True
    assert state["source"] == "generated"
    assert state["label"] == "Условная геометрия"
    assert state["generated"] is True and state["imported"] is False
    assert state["object_count"] == 2
    assert state["collector_count"] == 2
    assert state["asset_count"] == 8
    assert state["gallery_count"] >= 3
    assert body["source"] == "generated"
    assert body["properties"]["label"] == "Условная геометрия"
    assert body["properties"]["picket_m"] == 10
    features = body["features"]
    for feature in features:
        for lon, lat in coordinates(feature["geometry"]):
            assert BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]
    collectors = {
        f["properties"]["object_id"]: f for f in features if f["id"].startswith("collector-")
    }
    assert set(collectors) == {"3360", "5332"}
    assert all(f["geometry"]["type"] == "MultiLineString" for f in collectors.values())
    assert {f["properties"]["kind"] for f in features} == {"collector", "gallery", "asset"}
    assets = {f["id"]: f for f in features if f["properties"]["kind"] == "asset"}
    assert set(assets) == {"a1", "a2", "a3", "a4", "a5", "a6", "r1", "r2"}
    assert all(f["properties"]["asset_id"] == key for key, f in assets.items())
    assert assets["a1"]["properties"]["picket"] == "ПК47"
    assert assets["a1"]["properties"]["placement"] == "picket"
    assert assets["a3"]["properties"]["picket"] == "ПК48 · Г1 ПК5"
    assert assets["a3"]["properties"]["placement"] == "gallery"
    assert assets["a3"]["properties"]["gallery_id"] == assets["a4"]["properties"]["gallery_id"]
    assert assets["a5"]["properties"]["picket"] == "Г2 ПК0+5"
    assert assets["a6"]["properties"]["placement"] == "spread"
    assert assets["a6"]["properties"]["picket"] is None
    gap = meters(assets["a1"]["geometry"]["coordinates"], assets["a2"]["geometry"]["coordinates"])
    assert gap == pytest.approx(100, abs=2)
    gallery = next(f for f in features if f["id"] == assets["a3"]["properties"]["gallery_id"])
    assert gallery["properties"]["name"] == "Галерея Г1 · от ПК48"
    assert gallery["properties"]["basis"] == "channel_names"
    assert client.get("/api/v1/spatial", headers=headers).json() == body

    monkeypatch.setattr(get_settings(), "environment", "production")
    monkeypatch.setattr(get_settings(), "seed_demo", False)
    assert client.get("/api/v1/spatial", headers=headers).json()["source"] == "generated"


def test_import_takes_precedence_and_delete_restores_generated(
    client: TestClient, auth_users, ml_dir: Path
) -> None:
    seed_sources(ml_dir)
    admin = auth_users["admin"]
    imported = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "a1",
                "geometry": {"type": "Point", "coordinates": [37.61, 55.75]},
                "properties": {"kind": "asset", "asset_id": "a1"},
            }
        ],
    }
    assert client.put("/api/v1/spatial", headers=admin, json=imported).status_code == 200
    state = client.get("/api/v1/spatial/status", headers=admin).json()
    assert state["source"] == "import" and state["imported"] is True
    assert client.get("/api/v1/spatial", headers=admin).json()["source"] == "import"
    assert client.delete("/api/v1/spatial", headers=auth_users["viewer"]).status_code == 403

    reset = client.delete("/api/v1/spatial", headers=admin).json()

    assert reset["source"] == "generated"
    assert client.get("/api/v1/spatial", headers=admin).json()["source"] == "generated"


def test_wkt_import_accepts_lines_polygons_and_points(
    client: TestClient, auth_users, ml_dir: Path
) -> None:
    admin = auth_users["admin"]
    response = client.put(
        "/api/v1/spatial/wkt",
        headers=admin,
        json={
            "features": [
                {"id": "K-1", "wkt": "SRID=4326;LINESTRING (37.6 55.7, 37.61 55.71)"},
                {
                    "id": "G-1",
                    "wkt": "multilinestring((37.6 55.7,37.61 55.71),(37.62 55.72, 37.63 55.73))",
                    "kind": "gallery",
                    "object_id": "3360",
                },
                {"id": "Z-1", "wkt": " POLYGON ((37.6 55.7, 37.61 55.7, 37.61 55.71)) "},
                {"asset_id": "a1", "wkt": "POINT Z (37.64 55.75 12)"},
            ]
        },
    )

    assert response.status_code == 200
    features = {item["id"]: item for item in response.json()["features"]}
    assert features["K-1"]["geometry"] == {
        "type": "LineString",
        "coordinates": [[37.6, 55.7], [37.61, 55.71]],
    }
    assert features["K-1"]["properties"]["kind"] == "collector"
    assert features["G-1"]["geometry"]["type"] == "MultiLineString"
    assert features["G-1"]["properties"] == {
        "kind": "gallery",
        "source": "import_wkt",
        "object_id": "3360",
        "group_id": "3360",
    }
    ring = features["Z-1"]["geometry"]["coordinates"][0]
    assert features["Z-1"]["geometry"]["type"] == "Polygon"
    assert ring[0] == ring[-1] and len(ring) == 4
    assert features["a1"]["geometry"] == {"type": "Point", "coordinates": [37.64, 55.75]}
    assert features["a1"]["properties"]["asset_id"] == "a1"

    for text, message in (
        ("CIRCULARSTRING (1 2, 3 4)", "Неподдерживаемый тип"),
        ("POINT (55.75 137.64)", "вне WGS 84"),
        ("LINESTRING (37.6 55.7)", "не менее двух"),
        ("POINT EMPTY", "Пустая геометрия"),
        ("POINT (37.6 55.7) junk", "Лишние символы"),
    ):
        failed = client.put(
            "/api/v1/spatial/wkt", headers=admin, json={"features": [{"id": "x", "wkt": text}]}
        )
        assert failed.status_code == 422
        assert message in failed.json()["detail"]


def test_spatial_exports_geojson_and_wkt(client: TestClient, auth_users, ml_dir: Path) -> None:
    viewer = auth_users["viewer"]
    assert client.get("/api/v1/spatial.wkt", headers=viewer).status_code == 404
    seed_sources(ml_dir)

    generated = client.get("/api/v1/spatial.geojson", headers=viewer)
    lines = client.get("/api/v1/spatial.wkt", headers=viewer)

    assert generated.status_code == 200
    assert generated.headers["content-type"].startswith("application/geo+json")
    collection = json.loads(generated.content)
    assert collection["type"] == "FeatureCollection"
    assert collection["properties"]["source"] == "generated"
    assert lines.headers["content-type"].startswith("text/plain")
    rows = lines.text.strip().splitlines()
    assert len(rows) == len(collection["features"])
    assert rows[0].startswith("collector-") and ";MULTILINESTRING ((" in rows[0]
    by_id = {str(item["id"]): item["geometry"] for item in collection["features"]}
    for line in rows:
        identifier, text = line.split(";", 1)
        assert wkt.parse(text) == by_id[identifier]


def test_wkt_parser_round_trips_all_supported_types() -> None:
    samples = {
        "POINT (37.6 55.7)": "Point",
        "LINESTRING (37.6 55.7, 37.61 55.71)": "LineString",
        "POLYGON ((37.6 55.7, 37.61 55.7, 37.61 55.71, 37.6 55.7))": "Polygon",
        "MULTIPOINT ((37.6 55.7), (37.61 55.71))": "MultiPoint",
        "MULTILINESTRING ((37.6 55.7, 37.61 55.71), (37.62 55.72, 37.63 55.73))": (
            "MultiLineString"
        ),
        "MULTIPOLYGON (((37.6 55.7, 37.61 55.7, 37.61 55.71, 37.6 55.7)))": "MultiPolygon",
    }
    for text, kind in samples.items():
        geometry = wkt.parse(text)
        assert geometry["type"] == kind
        assert wkt.dumps(geometry) == text
    assert wkt.parse("MULTIPOINT (37.6 55.7, 37.61 55.71)") == wkt.parse(
        "MULTIPOINT ((37.6 55.7), (37.61 55.71))"
    )
    assert wkt.parse("pointzm(3.76e1 55.7 1 2)")["coordinates"] == [37.6, 55.7]
    with pytest.raises(wkt.WktError, match="EPSG:4326"):
        wkt.parse("SRID=3857;POINT (4187000 7509000)")


def test_channel_name_pickets_and_galleries() -> None:
    assert schematic.mark("Н1 ПК48 Г1 ПК5") == schematic.Mark(480, "ПК48", "1", 50, "Г1 ПК5")
    assert schematic.mark("ДД Г4 ПК0+2").main_m is None
    assert schematic.mark("ДД Г4 ПК0+2").gallery_m == 2
    assert schematic.mark("ДД ПК196+3,5(лев.)").main_m == 1963.5
    assert schematic.mark("ГРО4 ПК48 (ПК29-48) ГТ").gallery is None
    sideway = schematic.mark("АНС2 Н1 ПК305Гал.ПК2")
    assert (sideway.main_m, sideway.gallery, sideway.gallery_m) == (3050, "", 20)
    assert sideway.label == "ПК305 · Гал. ПК2"
    assert schematic.mark("Дым").label is None


def test_layout_keeps_objects_apart_inside_the_bbox() -> None:
    channels = [
        schematic.Channel(f"{index}-{picket}", str(index), f"Дым ПК{picket}", "", "")
        for index in range(60)
        for picket in (0, 400 + index * 20)
    ]
    collection = schematic.build(channels)
    boxes: dict[str, list[float]] = {}
    for feature in collection["features"]:
        for lon, lat in coordinates(feature["geometry"]):
            assert BBOX[0] <= lon <= BBOX[2] and BBOX[1] <= lat <= BBOX[3]
            box = boxes.setdefault(feature["properties"]["object_id"], [lon, lat, lon, lat])
            box[:] = [min(box[0], lon), min(box[1], lat), max(box[2], lon), max(box[3], lat)]
    names = sorted(boxes)
    for position, first in enumerate(names):
        for second in names[position + 1 :]:
            a, b = boxes[first], boxes[second]
            assert a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]
    for feature in collection["features"]:
        if feature["properties"]["kind"] == "collector":
            last = 400 + int(feature["properties"]["object_id"]) * 20
            assert feature["properties"]["picket_from"] == 0
            assert feature["properties"]["picket_to"] >= last
            assert feature["properties"]["length_m"] >= last * 10
    assert schematic.build(list(reversed(channels))) == collection
