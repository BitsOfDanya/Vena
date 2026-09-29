import io
import json
from unittest.mock import patch

import httpx
from openpyxl import Workbook
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.models import Equipment, HistoricalEvent, ImportOutbox
from app.db.session import SessionLocal
from app.domain import equipment, imports

CHANNEL_HEADERS = [
    "ид_канала_данных",
    "название_датчика",
    "тип_датчика",
    "тег_инженерной_системы",
    "тип_инж_системы",
    "ид_объект",
]
CHANNEL = ["001", "Насос ПК1", "Состояние насоса", "1.2.3.4", "Водоотведение", "12"]


def workbook(headers, rows):
    book = Workbook()
    book.active.append(headers)
    for row in rows:
        book.active.append(row)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def upload(client, headers, content, kind="channels", name="data.xlsx"):
    return client.post(
        f"/api/v1/imports?kind={kind}", headers=headers, files={"file": (name, content)}
    )


def test_channel_preview_apply_tree_and_rbac(client, auth_users, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "dataset_dir", tmp_path)
    content = workbook(CHANNEL_HEADERS, [CHANNEL])
    assert upload(client, auth_users["viewer"], content).status_code == 403
    assert upload(client, auth_users["dispatcher"], content).status_code == 403
    preview = upload(client, auth_users["admin"], content).json()
    assert preview["status"] == "validated"
    assert client.get("/api/v1/equipment", headers=auth_users["viewer"]).json()["total"] == 0
    result = client.post(f"/api/v1/imports/{preview['id']}/apply", headers=auth_users["admin"])
    assert result.status_code == 200, result.text
    assert result.json()["accepted"] == 1
    again = client.post(f"/api/v1/imports/{preview['id']}/apply", headers=auth_users["admin"])
    assert again.json()["accepted"] == 1
    tree = client.get("/api/v1/assets/tree", headers=auth_users["viewer"]).json()
    assert tree[0]["object_id"] == "12"
    assert tree[0]["sections"][0]["channels"][0]["probability"] is None
    with SessionLocal() as db:
        imports.publish_pending(db, get_settings())
    assert "ид_объект" in (tmp_path / "справочник_каналов_датчиков.csv").read_text()
    assert (tmp_path / ".revision").exists()


def test_invalid_formula_and_duplicate_files_are_atomic(client, auth_users, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "dataset_dir", tmp_path)
    for content in [
        workbook(CHANNEL_HEADERS, [CHANNEL, CHANNEL]),
        workbook(CHANNEL_HEADERS, [["=1+1", *CHANNEL[1:]]]),
        b"not an excel file",
    ]:
        response = upload(client, auth_users["admin"], content)
        assert response.status_code == 200, response.text
        run = response.json()
        assert run["status"] == "failed" and run["errors"]
        assert (
            client.post(
                f"/api/v1/imports/{run['id']}/apply", headers=auth_users["admin"]
            ).status_code
            == 409
        )
    assert client.get("/api/v1/equipment", headers=auth_users["admin"]).json()["total"] == 0


def test_journal_csv_deduplication_and_publication(client, auth_users, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "dataset_dir", tmp_path)
    run = upload(client, auth_users["admin"], workbook(CHANNEL_HEADERS, [CHANNEL])).json()
    client.post(f"/api/v1/imports/{run['id']}/apply", headers=auth_users["admin"])
    content = (
        "ид_события;ид_канала_данных;дата;время;тревожное;значение_датчика\n"
        "101;001;2026-01-01;12:00:00;t;Неисправен\n"
    ).encode("utf-8-sig")
    for expected in [1, 0]:
        preview = upload(client, auth_users["admin"], content, "journal", "events.csv").json()
        assert preview["status"] == "validated", preview
        result = client.post(f"/api/v1/imports/{preview['id']}/apply", headers=auth_users["admin"])
        assert result.status_code == 200, result.text
        assert result.json()["accepted"] == expected
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(HistoricalEvent)) == 1
        imports.publish_pending(db, get_settings())
    files = list((tmp_path / "uploads").glob("*.csv"))
    assert len(files) == 1
    assert "2026-01-01,12:00:00,t,Неисправен" in files[0].read_text()
    bad = content.replace(b"001", b"unknown")
    assert (
        upload(client, auth_users["admin"], bad, "journal", "events.csv").json()["status"]
        == "failed"
    )


def test_api_registry_updates_object_without_rebuild(client, auth_users):
    row = dict(asset_id="001", external_id="001", name="Насос", object_id="12")
    assert (
        client.put("/api/v1/equipment", headers=auth_users["admin"], json={"items": [row]}).json()[
            "created"
        ]
        == 1
    )
    row["object_id"] = "42"
    assert (
        client.put("/api/v1/equipment", headers=auth_users["admin"], json={"items": [row]}).json()[
            "updated"
        ]
        == 1
    )
    assert (
        client.get("/api/v1/assets/tree", headers=auth_users["viewer"]).json()[0]["object_id"]
        == "42"
    )

    row["status"] = "retired"
    assert (
        client.put(
            "/api/v1/equipment", headers=auth_users["admin"], json={"items": [row]}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/assets/tree", headers=auth_users["viewer"]).json() == []


def test_sync_pages_idempotence_and_failed_update_preserves_registry(
    client, auth_users, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "equipment_sync_enabled", True)
    monkeypatch.setattr(settings, "equipment_sync_url", "https://registry.example/equipment")
    calls = []

    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        if not request.url.params.get("cursor"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"asset_id": "1", "external_id": "a", "name": "Насос", "object_id": "12"}
                    ],
                    "next_cursor": "page2",
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {"asset_id": "2", "external_id": "b", "name": "Датчик", "object_id": "12"}
                ]
            },
        )

    real_client = httpx.Client
    with patch.object(
        equipment.httpx,
        "Client",
        side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    ):
        result = client.post("/api/v1/equipment/sync", headers=auth_users["admin"])
        assert result.json()["created"] == 2, result.text
        assert (
            client.post("/api/v1/equipment/sync", headers=auth_users["admin"]).json()["unchanged"]
            == 2
        )
    assert len(calls) == 4
    with patch.object(
        equipment, "fetch_registry", side_effect=ValueError("secret connection information")
    ):
        failure = client.post("/api/v1/equipment/sync", headers=auth_users["admin"]).json()
    assert failure["status"] == "failed" and "secret" not in json.dumps(failure)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Equipment)) == 2
        assert db.scalar(select(func.count()).select_from(ImportOutbox)) == 2
