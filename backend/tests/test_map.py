from io import BytesIO

from fastapi.testclient import TestClient

from app.db.models import ImportBatch
from app.db.seed_geo import seed_geo_demo
from app.db.session import SessionLocal
from app.domain.imports import process_batch


def test_geo_seed_is_idempotent_and_map_returns_connected_objects(client: TestClient) -> None:
    with SessionLocal() as session:
        seeded = seed_geo_demo(session)
        session.commit()
        assert seeded == {"objects": 117, "channels": 108, "events": 1512, "edges": 153}
        assert seed_geo_demo(session) == {"objects": 0, "channels": 0, "events": 0, "edges": 0}

    response = client.get("/api/v1/map/network")
    assert response.status_code == 200
    network = response.json()
    assert len(network["nodes"]) == 117
    assert len(network["edges"]) == 153
    ids = {node["id"] for node in network["nodes"]}
    assert all(55.5 < node["latitude"] < 56.0 for node in network["nodes"])
    assert all(edge["source_id"] in ids and edge["target_id"] in ids for edge in network["edges"])
    assert client.get("/api/v1/data/summary").json()["events"] == 1512


def _process_upload(client: TestClient, kind: str, filename: str, body: bytes) -> None:
    response = client.post(
        f"/api/v1/imports?kind={kind}",
        files={"file": (filename, BytesIO(body), "text/csv")},
    )
    assert response.status_code == 201, response.text
    with SessionLocal() as session:
        batch = session.get(ImportBatch, response.json()["id"])
        assert batch is not None
        process_batch(session, batch)
        assert batch.status == "completed"


def test_operator_can_import_geographic_objects_and_links(client: TestClient) -> None:
    client.post("/api/v1/auth/logout")
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "operator@example.com",
            "full_name": "Тестовый оператор",
            "password": "test-password-123",
            "role": "operator",
        },
    )
    objects = (
        "object_id,name,latitude,longitude,district,object_type\n"
        "OBJ-1,Узел 1,55.75,37.61,ЦАО,hub\n"
        "OBJ-2,Узел 2,55.76,37.62,ЦАО,pump\n"
    ).encode()
    _process_upload(client, "objects", "objects.csv", objects)
    links = b"source_id,target_id,kind\nOBJ-1,OBJ-2,collector\n"
    _process_upload(client, "edges", "links.csv", links)

    response = client.get("/api/v1/map/network")
    assert response.status_code == 200
    assert len(response.json()["nodes"]) == 2
    assert response.json()["edges"][0]["source_id"] == "OBJ-1"
