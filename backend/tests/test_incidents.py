import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.models import AuditLog, SituationClaim
from app.db.seed_users import create_user
from app.db.session import SessionLocal
from app.domain import hierarchy
from app.domain.incidents import remember_objects
from app.domain.predictions import reset_prediction_source

HIERARCHY = """ид_объект,иерархия_уровень,родитель,вид_объекта,диспетчерское_название_объекта
5122,3,5,controlHouse,ДУ объект Альфа
5123,3,5,controlHouse,ДП объект Альфа
165,3,6,guardObject,объект Бета
5773,1,3831,district,Район по эксплуатации
5,2,5773,controlHouse,объект Альфа
6,2,5773,controlHouse,объект Бета
"""
CHANNELS = {"100": ("5122", "5-1.1.1.1."), "300": ("165", "6-2.1.1.1.")}
PASSWORD = "incident-password-123"
REGISTRY = {
    "journal_end": "2026-06-30",
    "incidents": {
        "fire": {
            "label": "Пожарный инцидент",
            "rule": "Дым на двух датчиках за 15 минут",
            "total": 12,
            "objects": 2,
            "per_year": {"2025": 7, "2024": 5},
            "recent_2026h1": 3,
            "per_day_2026h1": 0.02,
            "channels_median": 2.0,
            "top_objects": {"5122": 8, "165": 4},
            "temperature_confirmed": 1,
        },
        "flood": {
            "label": "Подтопление",
            "rule": "Затоплен у двух насосов за час",
            "total": 5,
            "objects": 1,
            "per_year": {"2026": 5},
            "top_objects": {"165": 5},
            "long_over_30_minutes": 2,
        },
        "power": {
            "label": "Отключение питания объекта",
            "rule": "Обесточен у трёх фидеров за 5 минут",
            "total": 40,
            "objects": 2,
            "per_year": {"2026": 40},
            "top_objects": {"5122": 30, "165": 10},
        },
    },
}
RECENT = [
    {
        "kind": "power",
        "object": "165",
        "start": "2026-06-29T10:00:00",
        "end": "2026-06-29T10:20:00",
        "channels": 4,
        "temperature_confirmed": None,
        "max_minutes": None,
    },
    {
        "kind": "fire",
        "object": "5122",
        "start": "2026-06-29T14:03:11",
        "end": "2026-06-29T14:10:00",
        "channels": 3,
        "temperature_confirmed": True,
        "max_minutes": None,
    },
    {
        "kind": "flood",
        "object": "5122",
        "start": "2026-06-28T08:00:00",
        "end": None,
        "channels": 2,
        "temperature_confirmed": None,
        "max_minutes": 45.5,
    },
    {"kind": "unknown", "object": "5122", "start": "2026-06-28T08:00:00"},
]
OBJECTS = [
    {
        "object_id": "165",
        "scenario": "fire",
        "model_id": "object_fire_24h",
        "probability": 0.31,
        "rank": 1,
        "horizon_hours": 24,
        "history": {"1d": 0, "7d": 1, "30d": 2, "90d": 5, "days_since": 4},
        "channel_score": None,
    },
    {
        "object_id": "165",
        "scenario": "power_loss",
        "model_id": "object_power_24h",
        "probability": 0.52,
        "rank": 2,
        "horizon_hours": 24,
        "history": {"1d": 1, "7d": 3, "30d": 12, "90d": 30, "days_since": 0},
        "channel_score": 0.4,
    },
    {
        "object_id": "5122",
        "scenario": "power_loss",
        "model_id": "object_power_24h",
        "probability": 0.73,
        "rank": 1,
        "horizon_hours": 24,
        "history": {"1d": 0, "7d": 3, "30d": 12, "90d": 30, "days_since": 2},
        "channel_score": 0.91,
    },
    {
        "object_id": "5123",
        "scenario": "flooding",
        "model_id": "object_flood_24h",
        "probability": 0.44,
        "rank": 1,
        "horizon_hours": 24,
        "history": {"1d": 0, "7d": 0, "30d": 1, "90d": 2, "days_since": 40},
        "channel_score": 0.2,
        "probability_6h": 0.12,
    },
]
OBJECTS_META = {
    "object_power_24h": {
        "label": "Отключение питания объекта",
        "scenario": "power_loss",
        "precision_top3": 0.74,
        "base_rate": 0.54,
        "avg_precision": 0.83,
        "period": "2026H1",
        "rule": "Обесточен у трёх фидеров",
    },
    "object_flood_24h": {
        "label": "Подтопление",
        "scenario": "flooding",
        "precision_top3": 0.23,
        "base_rate": 0.07,
        "avg_precision": 0.28,
        "period": "2026H1",
        "rule": "Затоплен у двух насосов",
        "nowcast": {
            "model_id": "object_flood_6h",
            "horizon_hours": 6,
            "period": "2026H1",
            "share_top3": 0.65,
            "objects": 18,
        },
    },
    "object_fire_24h": {
        "label": "Пожарный инцидент",
        "scenario": "fire",
        "precision_top3": 0.2,
        "base_rate": 0.05,
        "avg_precision": 0.1,
        "period": "2026H1",
        "rule": "Дым на двух датчиках",
    },
}


def prediction_row(channel: str) -> dict:
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


def write_snapshot(ml: Path, snapshot_id: str, objects: bool = True) -> None:
    now = datetime.now(tz=UTC)
    payload: dict = {
        "snapshot_id": snapshot_id,
        "generated_at": now.isoformat(),
        "prediction_time": now.isoformat(),
        "models": {"pump_24h": {"version": "2026-09-16", "horizon_hours": 24}},
        "predictions": [prediction_row(channel) for channel in CHANNELS],
    }
    if objects:
        payload["objects"] = OBJECTS
        payload["objects_meta"] = OBJECTS_META
    path = ml / "results" / "predictions" / "snapshot.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    reset_prediction_source()


def write_registry(ml: Path, recent: bool = True) -> None:
    payload = dict(REGISTRY, recent=RECENT) if recent else REGISTRY
    path = ml / "results" / "incident_registry.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def ml(tmp_path: Path):
    settings = get_settings()
    original_ml, original_dataset = settings.ml_dir, settings.dataset_dir
    data = tmp_path / "dataset"
    data.mkdir()
    (data / hierarchy.FILE).write_text(HIERARCHY, encoding="utf-8")
    root = tmp_path / "ml"
    (root / "configs" / "models").mkdir(parents=True)
    (root / "configs" / "models" / "pump_24h.json").write_text("{}", encoding="utf-8")
    (root / "results" / "predictions").mkdir(parents=True)
    settings.ml_dir, settings.dataset_dir = root, data
    reset_prediction_source()
    yield root
    settings.ml_dir, settings.dataset_dir = original_ml, original_dataset
    reset_prediction_source()
    remember_objects({})
    hierarchy.load(settings)


@pytest.fixture()
def tokens(client, auth_users, ml):
    with SessionLocal.begin() as db:
        create_user(db, "tech", "tech@example.com", PASSWORD, "dispatcher", ["object:5122"])
        create_user(db, "beta", "beta@example.com", PASSWORD, "dispatcher", ["complex:6"])
        create_user(db, "second", "second@example.com", PASSWORD, "dispatcher")
    result = dict(auth_users)
    for name in ["tech", "beta", "second"]:
        response = client.post("/api/v1/auth/login", json={"login": name, "password": PASSWORD})
        assert response.status_code == 200, response.text
        result[name] = {"Authorization": "Bearer " + response.json()["access_token"]}
    client.cookies.clear()
    return result


def test_registry_is_empty_until_computed(client, ml):
    body = client.get("/api/v1/incidents/registry").json()

    assert body["available"] is False
    assert body["detail"] == "Реестр инцидентов ещё не рассчитан"
    assert body["kinds"] == [] and body["recent"] == []


def test_registry_without_recent_list_keeps_summaries(client, ml):
    write_registry(ml, recent=False)

    body = client.get("/api/v1/incidents/registry").json()

    assert body["available"] is True
    assert body["detail"] == "Список последних инцидентов ещё не рассчитан"
    assert [item["kind"] for item in body["kinds"]] == ["power", "flood", "fire"]
    assert body["recent"] == []


def test_registry_resolves_names_and_orders_recent(client, ml):
    write_registry(ml)

    body = client.get("/api/v1/incidents/registry").json()

    assert body["journal_end"] == "2026-06-30"
    assert body["restricted"] is False
    fire = next(item for item in body["kinds"] if item["kind"] == "fire")
    assert fire["label"] == "Пожарный инцидент"
    assert fire["per_year"] == [{"year": "2024", "count": 5}, {"year": "2025", "count": 7}]
    assert fire["top_objects"][0] == {
        "object_id": "5122",
        "object_name": "ДУ объект Альфа",
        "count": 8,
    }
    assert fire["temperature_confirmed"] == 1
    flood = next(item for item in body["kinds"] if item["kind"] == "flood")
    assert flood["long_over_30_minutes"] == 2
    assert [(item["kind"], item["object_id"]) for item in body["recent"]] == [
        ("fire", "5122"),
        ("power", "165"),
        ("flood", "5122"),
    ]
    first = body["recent"][0]
    assert first["object_name"] == "ДУ объект Альфа"
    assert first["label"] == "Пожарный инцидент"
    assert first["temperature_confirmed"] is True
    assert first["start"].startswith("2026-06-29T14:03:11")
    assert body["recent"][2]["max_minutes"] == pytest.approx(45.5)
    assert body["recent"][2]["end"] is None

    only_power = client.get("/api/v1/incidents/registry", params={"kind": "power"}).json()
    assert [item["kind"] for item in only_power["recent"]] == ["power"]
    assert client.get("/api/v1/incidents/registry", params={"kind": "gas"}).status_code == 422


def test_registry_follows_scope(client, tokens, ml):
    write_registry(ml)

    tech = client.get("/api/v1/incidents/registry", headers=tokens["tech"]).json()
    beta = client.get("/api/v1/incidents/registry", headers=tokens["beta"]).json()
    admin = client.get("/api/v1/incidents/registry", headers=tokens["admin"]).json()

    assert tech["restricted"] is True
    assert {item["object_id"] for item in tech["recent"]} == {"5122"}
    assert {item["object_id"] for item in beta["recent"]} == {"165"}
    assert len(admin["recent"]) == 3 and admin["restricted"] is False
    power = next(item for item in tech["kinds"] if item["kind"] == "power")
    assert [item["object_id"] for item in power["top_objects"]] == ["5122"]
    flood = next(item for item in tech["kinds"] if item["kind"] == "flood")
    assert flood["top_objects"] == []
    assert client.get("/api/v1/incidents/registry").status_code == 401


def test_objects_are_empty_until_computed(client, ml):
    assert client.get("/api/v1/incidents/objects").json()["detail"] == (
        "Утренний список объектов ещё не рассчитан"
    )
    write_snapshot(ml, "objects-0", objects=False)

    body = client.get("/api/v1/incidents/objects").json()

    assert body["available"] is False
    assert body["detail"] == "Утренний список объектов ещё не рассчитан"
    assert body["items"] == [] and body["models"] == []


def test_objects_join_meta_sorted_by_scenario_and_rank(client, ml):
    write_snapshot(ml, "objects-1")

    body = client.get("/api/v1/incidents/objects").json()

    assert body["available"] is True
    assert [(item["scenario"], item["rank"], item["object_id"]) for item in body["items"]] == [
        ("power_loss", 1, "5122"),
        ("power_loss", 2, "165"),
        ("flooding", 1, "5123"),
        ("fire", 1, "165"),
    ]
    first = body["items"][0]
    assert first["object_name"] == "ДУ объект Альфа"
    assert first["model_label"] == "Отключение питания объекта"
    assert first["probability"] == pytest.approx(0.73)
    assert first["history"] == {
        "events_1d": 0,
        "events_7d": 3,
        "events_30d": 12,
        "events_90d": 30,
        "days_since": 2.0,
    }
    assert first["channel_score"] == pytest.approx(0.91)
    assert body["items"][2]["model_label"] == "Подтопление"
    assert body["items"][2]["probability_6h"] == pytest.approx(0.12)
    assert first["probability_6h"] is None
    assert [item["model_id"] for item in body["models"]] == [
        "object_power_24h",
        "object_flood_24h",
        "object_fire_24h",
    ]
    assert body["models"][1]["nowcast"]["share_top3"] == pytest.approx(0.65)
    assert body["models"][0]["nowcast"] is None
    power = body["models"][0]
    assert power["precision_top3"] == pytest.approx(0.74)
    assert power["base_rate"] == pytest.approx(0.54)
    assert power["period"] == "2026H1"

    only_power = client.get(
        "/api/v1/incidents/objects", params={"scenario": "power_loss", "limit": 1}
    ).json()
    assert [item["object_id"] for item in only_power["items"]] == ["5122"]
    assert [item["model_id"] for item in only_power["models"]] == ["object_power_24h"]


def test_objects_follow_scope(client, tokens, ml):
    write_snapshot(ml, "objects-2")

    tech = client.get("/api/v1/incidents/objects", headers=tokens["tech"]).json()
    beta = client.get("/api/v1/incidents/objects", headers=tokens["beta"]).json()
    viewer = client.get("/api/v1/incidents/objects", headers=tokens["viewer"]).json()

    assert tech["restricted"] is True
    assert {item["object_id"] for item in tech["items"]} == {"5122"}
    assert {item["object_id"] for item in beta["items"]} == {"165"}
    assert len(viewer["items"]) == 4


def _situation(client, headers, object_id: str) -> dict:
    items = client.get("/api/v1/situations", headers=headers).json()
    return next(item for item in items if item["object_id"] == object_id)


def _claim_url(situation_id: str) -> str:
    return f"/api/v1/situations/{situation_id}/claim"


def test_claim_and_release_situation(client, tokens, ml):
    write_snapshot(ml, "claims-1")
    situation = _situation(client, tokens["dispatcher"], "5122")
    assert situation["claimed_by"] is None

    claimed = client.post(_claim_url(situation["id"]), headers=tokens["dispatcher"])
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["claimed_by"] == "dispatcher"
    again = client.post(_claim_url(situation["id"]), headers=tokens["dispatcher"])
    assert again.status_code == 200
    assert again.json()["claimed_at"] == claimed.json()["claimed_at"]

    seen = _situation(client, tokens["second"], "5122")
    assert seen["claimed_by"] == "dispatcher"
    assert seen["claimed_by_subject"] == "dispatcher"
    assert seen["claimed_at"] is not None
    assert _situation(client, tokens["second"], "165")["claimed_by"] is None

    taken = client.post(_claim_url(situation["id"]), headers=tokens["second"])
    assert taken.status_code == 409
    assert taken.json()["detail"] == "Ситуация уже в работе: её ведёт dispatcher"
    assert client.post(_claim_url(situation["id"]), headers=tokens["viewer"]).status_code == 403
    forbidden = client.delete(_claim_url(situation["id"]), headers=tokens["second"])
    assert forbidden.status_code == 403

    write_snapshot(ml, "claims-2")
    moved = _situation(client, tokens["second"], "5122")
    assert moved["id"] != situation["id"]
    assert moved["claimed_by"] == "dispatcher"

    released = client.delete(_claim_url(moved["id"]), headers=tokens["dispatcher"])
    assert released.status_code == 204
    assert _situation(client, tokens["second"], "5122")["claimed_by"] is None
    assert client.delete(_claim_url(moved["id"]), headers=tokens["dispatcher"]).status_code == 404

    with SessionLocal() as db:
        rows = db.execute(
            select(AuditLog.action, AuditLog.actor, AuditLog.resource_type, AuditLog.detail)
            .where(AuditLog.action.like("situation.%"))
            .order_by(AuditLog.id)
        ).all()
    assert [(row.action, row.actor, row.resource_type) for row in rows] == [
        ("situation.claim", "dispatcher", "situation"),
        ("situation.release", "dispatcher", "situation"),
    ]
    assert rows[0].detail == situation["title"]
    assert rows[1].detail == "Вёл: dispatcher"


def test_admin_releases_foreign_claim_and_scope_hides_situations(client, tokens, ml):
    write_snapshot(ml, "claims-3")
    beta_situation = _situation(client, tokens["admin"], "165")

    assert client.post(_claim_url(beta_situation["id"]), headers=tokens["tech"]).status_code == 404
    assert client.post(_claim_url(beta_situation["id"]), headers=tokens["beta"]).status_code == 200
    assert client.post(
        _claim_url("situation-x:fire:nowhere"), headers=tokens["beta"]
    ).status_code == (404)

    released = client.delete(_claim_url(beta_situation["id"]), headers=tokens["admin"])
    assert released.status_code == 204
    with SessionLocal() as db:
        assert db.scalars(select(SituationClaim)).all() == []
        audit = db.execute(
            select(AuditLog.actor, AuditLog.detail).where(AuditLog.action == "situation.release")
        ).one()
    assert audit.actor == "admin"
    assert audit.detail == "Вёл: beta"


def test_claim_without_auth_uses_duty_name(client, ml):
    write_snapshot(ml, "claims-4")
    situation = client.get("/api/v1/situations").json()[0]

    response = client.post(_claim_url(situation["id"]))

    assert response.status_code == 200
    assert response.json()["claimed_by"] == "Дежурный инженер"
    assert client.get("/api/v1/situations").json()[0]["claimed_by"] == "Дежурный инженер"


def test_claims_migration_upgrades_and_downgrades(monkeypatch) -> None:
    schema = "migration_" + uuid4().hex[:12]
    engine = create_engine(get_settings().database_url, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))

    def tables() -> set[str]:
        return set(inspect(engine).get_table_names(schema))

    try:
        command.upgrade(config, "heads")
        assert "situation_claims" in tables()
        columns = {
            column["name"] for column in inspect(engine).get_columns("situation_claims", schema)
        }
        assert columns == {
            "situation_key",
            "situation_id",
            "subject",
            "display_name",
            "claimed_at",
        }
        command.downgrade(config, "b7d41c9e5a22")
        assert "situation_claims" not in tables()
        assert "actions" in tables()
        command.upgrade(config, "4d932c29b262")
        assert "situation_claims" in tables()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
