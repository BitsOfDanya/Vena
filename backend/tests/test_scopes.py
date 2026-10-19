import io
import json
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, inspect, select, text

from app.core import ldap
from app.core.config import Settings, get_settings
from app.db.models import AuditLog, Equipment, HistoricalEvent, User
from app.db.seed_users import create_user, seed_scopes, seed_users
from app.db.session import SessionLocal
from app.domain import hierarchy
from app.domain.incidents import location_label, remember_objects
from app.domain.predictions import reset_prediction_source

HIERARCHY = """ид_объект,иерархия_уровень,родитель,вид_объекта,диспетчерское_название_объекта
5122,3,5,controlHouse,ДУ объект Альфа
5123,3,5,controlHouse,ДП объект Альфа
165,3,6,guardObject,объект Бета
5773,1,3831,district,Район по эксплуатации
5,2,5773,controlHouse,объект Альфа
6,2,5773,controlHouse,объект Бета
"""
CHANNELS = {
    "100": ("5122", "5-1.1.1.1."),
    "200": ("5123", "5-1.1.2.1."),
    "300": ("165", "6-2.1.1.1."),
}
PASSWORD = "scope-password-123"


def snapshot_row(channel: str) -> dict:
    object_id, tag = CHANNELS[channel]
    return {
        "channel_id": channel,
        "device_type": "pump",
        "model_id": "pump_24h",
        "model_version": "2026-09-16",
        "horizon_hours": 24,
        "score": 0.97,
        "score_type": "calibrated_probability",
        "model_risk_level": "critical",
        "tag": tag,
        "object_id": object_id,
        "name": f"Насос {channel}",
    }


@pytest.fixture()
def dataset(tmp_path: Path):
    settings = get_settings()
    original_ml, original_dataset = settings.ml_dir, settings.dataset_dir
    data = tmp_path / "dataset"
    data.mkdir()
    (data / hierarchy.FILE).write_text(HIERARCHY, encoding="utf-8")
    ml = tmp_path / "ml"
    (ml / "configs" / "models").mkdir(parents=True)
    (ml / "configs" / "models" / "pump_24h.json").write_text("{}", encoding="utf-8")
    (ml / "results" / "predictions").mkdir(parents=True)
    (ml / "results" / "directions.json").write_text("[]", encoding="utf-8")
    now = datetime.now(tz=UTC)
    payload = {
        "snapshot_id": "scope-1",
        "generated_at": now.isoformat(),
        "prediction_time": now.isoformat(),
        "models": {"pump_24h": {"version": "2026-09-16", "horizon_hours": 24}},
        "predictions": [snapshot_row(channel) for channel in CHANNELS],
        "alarms": [
            {
                "channel_id": channel,
                "ts": now.isoformat(),
                "sensor_type": "Датчик дыма",
                "corroboration_probability": 0.5,
                "needs_verification": True,
                "tag": CHANNELS[channel][1],
            }
            for channel in CHANNELS
        ],
    }
    (ml / "results" / "predictions" / "snapshot.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    settings.ml_dir, settings.dataset_dir = ml, data
    reset_prediction_source()
    yield data
    settings.ml_dir, settings.dataset_dir = original_ml, original_dataset
    reset_prediction_source()
    remember_objects({})
    hierarchy.load(settings)


@pytest.fixture()
def scoped(client, auth_users, dataset):
    with SessionLocal.begin() as db:
        create_user(
            db, "district", "district@example.com", PASSWORD, "dispatcher", ["district:5773"]
        )
        create_user(db, "alpha", "alpha@example.com", PASSWORD, "dispatcher", ["complex:5"])
        create_user(db, "tech", "tech@example.com", PASSWORD, "dispatcher", ["object:5122"])
        for channel, (object_id, tag) in CHANNELS.items():
            db.add(
                Equipment(
                    asset_id=channel,
                    external_id=channel,
                    source="customer",
                    name=f"Насос {channel}",
                    object_id=object_id,
                    tag=tag,
                )
            )
            db.add(
                HistoricalEvent(
                    event_id=f"E{channel}",
                    channel_id=channel,
                    ts=datetime.now(tz=UTC) - timedelta(minutes=5),
                    value="Неисправен",
                    alarm=True,
                )
            )
    tokens = dict(auth_users)
    for name in ["district", "alpha", "tech"]:
        response = client.post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
        assert response.status_code == 200, response.text
        tokens[name] = {"Authorization": "Bearer " + response.json()["access_token"]}
    client.cookies.clear()
    for channel in CHANNELS:
        created = client.post(
            "/api/v1/actions",
            headers=tokens["admin"],
            json={
                "asset_id": channel,
                "kind": "inspect",
                "reason": "Риск",
                "priority": "high",
                "recommended_at": datetime.now(tz=UTC).isoformat(),
                "source": "vena_forecast",
                "source_model_id": "pump_24h",
                "status": "suggested",
            },
        )
        assert created.status_code == 201, created.text
    return tokens


def visible(client, path: str, headers: dict, key: str = "asset_id") -> set[str]:
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return {item[key] for item in response.json()}


def test_users_with_different_scopes_see_different_data(client, scoped):
    expected = {
        "admin": {"100", "200", "300"},
        "dispatcher": {"100", "200", "300"},
        "district": {"100", "200", "300"},
        "alpha": {"100", "200"},
        "tech": {"100"},
    }
    for user, channels in expected.items():
        headers = scoped[user]
        assert visible(client, "/api/v1/predictions", headers) == channels
        assert client.get("/api/v1/predictions/summary", headers=headers).json()["total"] == len(
            channels
        )
        situations = client.get("/api/v1/situations", headers=headers).json()
        assert {asset for item in situations for asset in item["asset_ids"]} == channels
        assert visible(client, "/api/v1/actions", headers) == channels
        assert visible(client, "/api/v1/alarms", headers, "channel_id") == channels
        assert visible(client, "/api/v1/journal", headers) == channels
        events = client.get("/api/v1/events/recent", headers=headers).json()["items"]
        assert {item["channel_id"] for item in events} == channels
        tree = client.get("/api/v1/assets/tree", headers=headers).json()
        assert {
            channel["asset_id"]
            for node in tree
            for section in node["sections"]
            for channel in section["channels"]
        } == channels
        report = client.get("/api/v1/reports/predictions.csv", headers=headers).text
        assert {line.split(",")[1] for line in report.splitlines()[1:]} == channels
    situation = client.get("/api/v1/situations", headers=scoped["tech"]).json()[0]
    assert situation["location"] == "ДУ объект Альфа · 5-1.1.1"
    assert situation["object_id"] == "5122"


def test_out_of_scope_items_return_404(client, scoped):
    listed = client.get("/api/v1/actions", headers=scoped["admin"]).json()
    actions = {item["asset_id"]: item["id"] for item in listed}
    foreign = actions["300"]
    tech = scoped["tech"]
    assert client.get(f"/api/v1/actions/{foreign}", headers=tech).status_code == 404
    assert client.post(f"/api/v1/actions/{foreign}/approve", headers=tech).status_code == 404
    assert client.get(f"/api/v1/actions/{foreign}", headers=scoped["alpha"]).status_code == 404
    assert client.get(f"/api/v1/actions/{actions['100']}", headers=tech).status_code == 200
    approved = client.post(f"/api/v1/actions/{actions['100']}/approve", headers=tech)
    assert approved.status_code == 200
    assert client.get("/api/v1/actions/A-404", headers=tech).status_code == 404
    body = {
        "asset_id": "300",
        "kind": "inspect",
        "reason": "Риск",
        "priority": "high",
        "recommended_at": datetime.now(tz=UTC).isoformat(),
    }
    assert client.post("/api/v1/actions", headers=tech, json=body).status_code == 404
    prediction = "scope-1:pump_24h:300"
    assert client.get(f"/api/v1/predictions/{prediction}", headers=tech).status_code == 404
    assert client.get(f"/api/v1/predictions/{prediction}", headers=scoped["district"]).is_success
    assert client.get("/api/v1/assets/300/prediction", headers=tech).status_code == 404
    assert client.get("/api/v1/assets/300/predictions", headers=tech).status_code == 404
    notification = client.post(
        "/api/v1/notifications",
        headers=scoped["admin"],
        json={"type": "risk", "severity": "info", "title": "Риск", "asset_id": "300"},
    ).json()
    shared = client.post(
        "/api/v1/notifications",
        headers=scoped["admin"],
        json={"type": "integration", "severity": "info", "title": "Пакет событий"},
    ).json()
    listed = {item["id"] for item in client.get("/api/v1/notifications", headers=tech).json()}
    assert shared["id"] in listed and notification["id"] not in listed
    path = f"/api/v1/notifications/{notification['id']}"
    assert client.get(path, headers=tech).status_code == 404
    assert client.patch(path, headers=tech, json={"read": True}).status_code == 404
    assert client.get(path, headers=scoped["alpha"]).status_code == 404
    assert client.get(path, headers=scoped["dispatcher"]).status_code == 200


def test_spatial_registry_and_shift_report_follow_scope(client, scoped):
    def point(kind: str, **properties) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [37.6, 55.7]},
            "properties": {"kind": kind, **properties},
        }

    layer = {
        "type": "FeatureCollection",
        "features": [
            point("corridor"),
            point("collector", group_id="K-1"),
            point("collector", group_id="K-2"),
            point("collector", group_id="K-3", object_id="165"),
            point("asset", asset_id="100", group_id="K-1"),
            point("asset", asset_id="300", group_id="K-2"),
        ],
    }
    assert client.put("/api/v1/spatial", headers=scoped["admin"], json=layer).status_code == 200
    features = client.get("/api/v1/spatial", headers=scoped["tech"]).json()["features"]
    assert [item["properties"].get("group_id") for item in features] == [None, "K-1", "K-1"]
    assert len(client.get("/api/v1/spatial", headers=scoped["dispatcher"]).json()["features"]) == 6
    registry = client.get("/api/v1/equipment", headers=scoped["alpha"]).json()
    assert registry["total"] == 2
    report = client.get("/api/v1/reports/shift", headers=scoped["tech"]).json()
    assert report["predicted"]["total"] == 1
    assert report["done"]["open"] == 1
    effect = client.get("/api/v1/analytics/effect", headers=scoped["alpha"]).json()
    assert effect["channels_at_risk"] == 2 and effect["alarms_30d"] == 2


def test_scope_label_tree_and_login_audit(client, scoped):
    me = {
        name: client.get("/api/v1/auth/me", headers=scoped[name]).json()
        for name in ["admin", "alpha", "tech"]
    }
    assert me["admin"]["scope_label"] == "Все объекты"
    assert me["alpha"]["scopes"] == ["complex:5"]
    assert me["alpha"]["scope_label"] == "объект Альфа"
    assert me["tech"]["scope_label"] == "ДУ объект Альфа"
    full = client.get("/api/v1/objects/tree", headers=scoped["admin"]).json()
    assert full["available"] is True
    district = full["districts"][0]
    assert district["name"] == "Район по эксплуатации" and district["channels"] == 3
    assert [item["name"] for item in district["complexes"]] == ["объект Альфа", "объект Бета"]
    alpha = district["complexes"][0]
    assert alpha["channels"] == 2
    assert [item["name"] for item in alpha["objects"]] == ["ДП объект Альфа", "ДУ объект Альфа"]
    tech = client.get("/api/v1/objects/tree", headers=scoped["tech"]).json()
    assert [
        leaf["id"]
        for node in tech["districts"]
        for item in node["complexes"]
        for leaf in item["objects"]
    ] == ["5122"]
    with SessionLocal() as db:
        detail = db.scalar(
            select(AuditLog.detail).where(AuditLog.action == "auth.login", AuditLog.actor == "tech")
        )
    assert detail == "scopes=object:5122"


def test_admin_edits_local_scopes(client, scoped):
    users = client.get("/api/v1/users", headers=scoped["admin"]).json()["items"]
    tech = next(user for user in users if user["username"] == "tech")
    assert tech["scopes"] == ["object:5122"] and tech["scope_label"] == "ДУ объект Альфа"
    path = f"/api/v1/users/{tech['id']}"
    admin = scoped["admin"]
    for invalid in [[], ["region:1"], [" "]]:
        assert client.patch(path, headers=admin, json={"scopes": invalid}).status_code == 422
    updated = client.patch(path, headers=admin, json={"scopes": ["object:165", "complex:5"]})
    assert updated.status_code == 200
    assert updated.json()["scope_label"] == "объект Бета, объект Альфа"
    response = client.post(
        "/api/v1/auth/login", json={"login": "tech", "password": PASSWORD}
    ).json()
    client.cookies.clear()
    headers = {"Authorization": "Bearer " + response["access_token"]}
    assert visible(client, "/api/v1/predictions", headers) == {"100", "200", "300"}
    everything = client.patch(path, headers=admin, json={"scopes": ["object:165", "all"]})
    assert everything.json()["scopes"] == ["all"]
    created = client.post(
        "/api/v1/users",
        headers=admin,
        json={
            "username": "beta",
            "email": "beta@example.com",
            "password": PASSWORD,
            "role": "viewer",
            "scopes": ["complex:6"],
        },
    )
    assert created.status_code == 201 and created.json()["scope_label"] == "объект Бета"


def test_ldap_group_scopes_are_additive(client, auth_users, dataset, monkeypatch):
    settings = Settings(
        _env_file=None,
        ldap_group_scopes={
            "CN=VENA-Alpha,OU=Groups,DC=example": ["complex:5"],
            "vena-beta": ["object:165", "complex:5"],
            "vena-ods": ["all"],
        },
    )
    alpha = "cn=vena-alpha,ou=groups,dc=example"
    assert ldap.group_scopes(settings, [alpha]) == ("complex:5",)
    assert ldap.group_scopes(settings, [alpha, "CN=VENA-Beta,DC=example"]) == (
        "complex:5",
        "object:165",
    )
    assert ldap.group_scopes(settings, [alpha, "CN=VENA-ODS,DC=example"]) == ("all",)
    assert ldap.group_scopes(settings, ["CN=Other,DC=example"]) == ("all",)
    strict = Settings(_env_file=None, ldap_default_scopes=[])
    assert ldap.group_scopes(strict, ["CN=Other,DC=example"]) == ()
    with pytest.raises(ValueError):
        Settings(_env_file=None, ldap_group_scopes={"x": ["region:1"]})

    directory = Settings(
        _env_file=None,
        ldap_enabled=True,
        ldap_url="ldaps://directory.example",
        ldap_bind_dn="cn=service,dc=example",
        ldap_bind_password=SecretStr("service-secret"),
        ldap_base_dn="dc=example",
        ldap_group_scopes=settings.ldap_group_scopes,
    )
    service = Mock(result={"result": 0})
    service.response = [
        {
            "type": "searchResEntry",
            "dn": "cn=ivan,dc=example",
            "attributes": {
                "sAMAccountName": ["ivan"],
                "objectGUID": ["guid"],
                "mail": ["ivan@example.com"],
                "memberOf": ["CN=VENA-Alpha,OU=Groups,DC=example", "CN=vena-beta,DC=example"],
            },
        }
    ]
    monkeypatch.setattr(ldap, "_connect", Mock(side_effect=[service, Mock()]))
    identity = ldap.authenticate(directory, "ivan", "password")
    assert identity.scopes == ("complex:5", "object:165")

    monkeypatch.setattr(ldap, "authenticate", lambda *args: identity)
    response = client.post("/api/v1/auth/ldap", json={"login": "ivan", "password": "secret"})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["scopes"] == ["complex:5", "object:165"]
    client.cookies.clear()
    token = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert visible(client, "/api/v1/predictions", token) == {"100", "200", "300"}
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "ldap:ivan"))
        assert user is not None
        user_id = user.id
        audit = db.scalar(select(AuditLog.detail).where(AuditLog.action == "auth.ldap_login"))
    assert audit == "scopes=complex:5,object:165"
    reduced = ldap.DirectoryIdentity(
        identity.directory_id, identity.username, identity.email, "dispatcher", ("object:5122",)
    )
    monkeypatch.setattr(ldap, "authenticate", lambda *args: reduced)
    token = {
        "Authorization": "Bearer "
        + client.post("/api/v1/auth/ldap", json={"login": "ivan", "password": "secret"}).json()[
            "access_token"
        ]
    }
    client.cookies.clear()
    assert visible(client, "/api/v1/predictions", token) == {"100"}
    assert (
        client.patch(
            f"/api/v1/users/{user_id}", headers=auth_users["admin"], json={"scopes": ["all"]}
        ).status_code
        == 400
    )


def test_hierarchy_loader_reads_and_caches_csv(tmp_path: Path):
    settings = Settings(_env_file=None, dataset_dir=tmp_path)
    assert hierarchy.load(settings) is hierarchy.EMPTY
    path = tmp_path / hierarchy.FILE
    path.write_text(HIERARCHY, encoding="utf-8")
    loaded = hierarchy.load(settings)
    assert loaded.name("5") == "объект Альфа"
    assert loaded.under("5") == {"5", "5122", "5123"}
    assert loaded.under("5773") == {"5773", "5", "6", "5122", "5123", "165"}
    assert loaded.under("999") == {"999"}
    assert hierarchy.load(settings) is loaded
    remember_objects({"5-1.1.1": "5122"})
    assert location_label("5-1.1.1") == "ДУ объект Альфа · 5-1.1.1"
    assert location_label("15-2.1") == "Объект 15 · 2.1"
    path.write_text(HIERARCHY.replace("ДУ объект Альфа", "ДУ Альфа"), encoding="utf-8")
    stamp = time.time() + 5
    os.utime(path, (stamp, stamp))
    assert hierarchy.load(settings).name("5122") == "ДУ Альфа"
    path.write_text("broken\n\x00", encoding="utf-8")
    os.utime(path, (stamp + 5, stamp + 5))
    assert hierarchy.load(settings).nodes == {}
    path.unlink()
    assert hierarchy.load(settings) is hierarchy.EMPTY
    assert location_label("5-1.1.1") == "Объект 5122 · 5-1.1.1"
    remember_objects({})


def test_objects_import_replaces_hierarchy(client, auth_users, monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "dataset_dir", tmp_path)
    monkeypatch.setattr(get_settings(), "ml_dir", tmp_path / "ml")
    reset_prediction_source()
    assert client.get("/api/v1/objects/tree", headers=auth_users["admin"]).json() == {
        "available": False,
        "districts": [],
        "unassigned": [],
    }
    content = HIERARCHY.encode("utf-8")
    preview = client.post(
        "/api/v1/imports?kind=objects",
        headers=auth_users["admin"],
        files={"file": ("objects.csv", io.BytesIO(content))},
    ).json()
    assert preview["status"] == "validated", preview
    applied = client.post(f"/api/v1/imports/{preview['id']}/apply", headers=auth_users["admin"])
    assert applied.status_code == 200 and applied.json()["accepted"] == 6
    assert "ДУ объект Альфа" in (tmp_path / hierarchy.FILE).read_text(encoding="utf-8")
    tree = client.get("/api/v1/objects/tree", headers=auth_users["viewer"]).json()
    assert tree["districts"][0]["complexes"][0]["name"] == "объект Альфа"
    broken = client.post(
        "/api/v1/imports?kind=objects",
        headers=auth_users["admin"],
        files={"file": ("objects.csv", io.BytesIO(content.replace(b",3,5,", b",7,5,")))},
    ).json()
    assert broken["status"] == "failed"
    template = client.get("/api/v1/imports/template/objects.xlsx", headers=auth_users["admin"])
    assert template.status_code == 200
    monkeypatch.setattr(get_settings(), "dataset_dir", None)
    hierarchy.load(get_settings())
    monkeypatch.undo()
    reset_prediction_source()


def test_seed_scopes_only_for_new_accounts(client):
    assert seed_scopes(None) == {}
    scopes = seed_scopes('{"USER18": ["complex:5", "complex:5"], "user19": ["object:5122"]}')
    assert scopes == {"user18": ["complex:5"], "user19": ["object:5122"]}
    with pytest.raises(ValueError):
        seed_scopes('{"user18": "complex:5"}')
    with pytest.raises(ValueError):
        seed_scopes('{"user18": ["region:5"]}')
    with SessionLocal.begin() as db:
        create_user(db, "user1", "user1@example.com", "0987654321", "admin")
        assert seed_users(db, scopes=scopes) == 19
        users = {user.username: user for user in db.scalars(select(User))}
        assert users["user1"].role == "admin" and users["user1"].scopes == ["all"]
        assert users["user18"].scopes == ["complex:5"]
        assert users["user19"].scopes == ["object:5122"]
        assert users["user2"].scopes == ["all"]
        assert seed_users(db, scopes={"user2": ["object:1"]}) == 0
        assert db.get(User, users["user2"].id).scopes == ["all"]


def test_scopes_migration_upgrade_and_downgrade(monkeypatch):
    settings = get_settings()
    schema = "scopes_migration"
    admin = create_engine(settings.database_url)
    try:
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
            connection.execute(text(f"CREATE SCHEMA {schema}"))
        monkeypatch.setenv("PGOPTIONS", f"-c search_path={schema}")
        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        command.upgrade(config, "04ab71cd902e")
        probe = create_engine(settings.database_url)
        try:

            def columns() -> set[str]:
                with probe.connect() as connection:
                    return {item["name"] for item in inspect(connection).get_columns("users")}

            assert "scopes" not in columns()
            with probe.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO users (id, username, email, password_hash, role, is_active,"
                        " created_at) VALUES ('u1', 'old', 'old@example.com', 'x', 'viewer', true,"
                        " now())"
                    )
                )
            command.upgrade(config, "b8e4f2a91c57")
            assert "scopes" in columns()
            with probe.connect() as connection:
                assert connection.scalar(text("SELECT scopes::text FROM users")) == '["all"]'
            command.downgrade(config, "04ab71cd902e")
            assert "scopes" not in columns()
            command.upgrade(config, "b8e4f2a91c57")
            assert "scopes" in columns()
        finally:
            probe.dispose()
    finally:
        monkeypatch.delenv("PGOPTIONS", raising=False)
        with admin.begin() as connection:
            connection.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        admin.dispose()
