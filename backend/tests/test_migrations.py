import importlib.util
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_legacy_forecast_texts_are_translated() -> None:
    texts = _load("b5d1e7c3a9f2_russian_forecast_texts")

    assert texts._reason(
        "Потеря питания · Объект 854 · 1.1.9: ML phase_24h critical risk 89% over 24h; "
        "2 channels at this location"
    ) == (
        "Прогноз: потеря питания, критично, 89% за 24 ч. Место: Объект 854 · 1.1.9. "
        "Каналов на локации: 2."
    )
    assert (
        texts._reason(
            "Подтопление · Объект 16 · 2.1.1: модель flood_24h, уровень внимание, "
            "вероятность 41% за 24 ч"
        )
        == "Прогноз: подтопление, внимание, 41% за 24 ч. Место: Объект 16 · 2.1.1."
    )
    assert texts._reason("Осмотр фидера") is None
    assert texts._description(
        "Model smoke_24h reports attention risk for the next 24h, +0.012 since the previous "
        "snapshot. 2 channels at this location share the risk. Main reason: Эпизодов за 3 сут: 1."
    ) == (
        "Прогноз «Пожар, сутки»: уровень внимание на 24 ч, изменение +0.012 с прошлого "
        "снимка. Риск разделяют каналов на локации: 2. Главная причина: Эпизодов за 3 сут: 1."
    )
    assert texts._description(
        "Модель phase_24h: уровень критично на 24 ч. Главная причина: Рост частоты событий: 2."
    ) == (
        "Прогноз «Питание, сутки»: уровень критично на 24 ч. "
        "Главная причина: Рост частоты событий: 2."
    )
    assert (
        texts._title("Потеря питания · Объект 854 · 1.1.9 · phase_24h 83%")
        == "Потеря питания · Объект 854 · 1.1.9 · 83% за 24 ч"
    )
    assert texts._title("P-0142 · риск 68/100") is None


def test_helpdesk_migration_upgrades_and_downgrades(monkeypatch) -> None:
    schema = "migration_" + uuid4().hex[:12]
    engine = create_engine(get_settings().database_url, poolclass=NullPool)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "migrations"))

    def columns() -> set[str]:
        return {column["name"] for column in inspect(engine).get_columns("actions", schema)}

    try:
        command.upgrade(config, "heads")
        assert {"helpdesk_ticket_id", "helpdesk_status"} <= columns()
        command.downgrade(config, "04ab71cd902e")
        assert not {"helpdesk_ticket_id", "helpdesk_status"} & columns()
        command.upgrade(config, "b7d41c9e5a22")
        assert {"helpdesk_ticket_id", "helpdesk_status"} <= columns()
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
