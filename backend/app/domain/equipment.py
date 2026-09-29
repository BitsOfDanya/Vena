import csv
import json
import os
import ssl
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Equipment, ImportOutbox, IntegrationRun, utcnow
from app.domain import audit
from app.schemas.equipment import EquipmentIn


class RegistryError(ValueError):
    pass


def lock_registry(session: Session) -> None:
    if not session.scalar(text("SELECT pg_try_advisory_xact_lock(78204101)")):
        raise RegistryError("Реестр уже обновляется. Повторите позже.")


def upsert(session: Session, rows: list[EquipmentIn], source: str) -> dict:
    counts = {"created": 0, "updated": 0, "unchanged": 0}
    assets = {row.asset_id for row in rows}
    external = {row.external_id for row in rows}
    if len(assets) != len(rows) or len(external) != len(rows):
        raise RegistryError("Повторяется идентификатор канала или внешний идентификатор.")
    existing = {}
    links = {}
    for offset in range(0, len(rows), 1000):
        batch = rows[offset : offset + 1000]
        existing.update(
            {
                row.asset_id: row
                for row in session.scalars(
                    select(Equipment).where(
                        Equipment.asset_id.in_([item.asset_id for item in batch])
                    )
                )
            }
        )
        links.update(
            {
                row.external_id: row.asset_id
                for row in session.scalars(
                    select(Equipment).where(
                        Equipment.source == source,
                        Equipment.external_id.in_([item.external_id for item in batch]),
                    )
                )
            }
        )
    for row in rows:
        current = existing.get(row.asset_id)
        if row.external_id in links and links[row.external_id] != row.asset_id:
            raise RegistryError("Внешний идентификатор уже связан с другим каналом.")
        if current and (current.source != source or current.external_id != row.external_id):
            raise RegistryError(
                f"Канал {row.asset_id} уже связан с другим источником или идентификатором."
            )
        values = row.model_dump()
        if current is None:
            session.add(Equipment(**values, source=source, updated_at=utcnow()))
            counts["created"] += 1
        elif any(getattr(current, key) != value for key, value in values.items()):
            for key, value in values.items():
                setattr(current, key, value)
            current.updated_at = utcnow()
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1
    session.flush()
    return counts


def queue_registry(session: Session) -> None:
    session.add(ImportOutbox(id=uuid4().hex, payload=json.dumps({"kind": "channels"})))


def publish_registry(session: Session, settings: Settings) -> None:
    if settings.dataset_dir is None:
        return
    target = settings.dataset_dir / "справочник_каналов_датчиков.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "ид_канала_данных",
                "название_датчика",
                "тип_датчика",
                "тег_инженерной_системы",
                "тип_инж_системы",
                "ид_объект",
            ]
        )
        for row in session.scalars(
            select(Equipment).where(Equipment.status != "retired").order_by(Equipment.asset_id)
        ):
            writer.writerow(
                [
                    row.asset_id,
                    row.name,
                    row.equipment_type,
                    row.tag,
                    row.system_type,
                    row.object_id,
                ]
            )
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(target)


def fetch_registry(settings: Settings) -> list[EquipmentIn]:
    url = urlsplit(settings.equipment_sync_url)
    if (
        not url.hostname
        or url.username
        or url.password
        or url.fragment
        or (
            url.scheme != "https"
            and not (url.scheme == "http" and settings.equipment_sync_allow_http)
        )
    ):
        raise RegistryError("Задайте HTTPS-адрес учётной системы на сервере.")
    headers = {"Accept": "application/json"}
    token = settings.equipment_sync_token.get_secret_value()
    if token:
        headers["Authorization"] = "Bearer " + token
    verify = ssl.create_default_context(cafile=settings.equipment_sync_ca_file)
    rows: list[EquipmentIn] = []
    cursor = None
    cursors: set[str] = set()
    with httpx.Client(timeout=20, verify=verify, follow_redirects=False, trust_env=False) as client:
        for _ in range(100):
            with client.stream(
                "GET",
                settings.equipment_sync_url,
                headers=headers,
                params={"cursor": cursor} if cursor else None,
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 10_000_000:
                        raise RegistryError("Ответ учётной системы превышает 10 МБ на страницу.")
            data = json.loads(content)
            items = data if isinstance(data, list) else data.get("items")
            if not isinstance(items, list):
                raise RegistryError("В ответе учётной системы отсутствует массив items.")
            for item in items:
                if settings.equipment_sync_field_map:
                    mapped = {}
                    for field, path in settings.equipment_sync_field_map.items():
                        value = item
                        for key in path.split("."):
                            value = value.get(key) if isinstance(value, dict) else None
                        if value is not None:
                            mapped[field] = value
                    item = mapped
                rows.append(EquipmentIn.model_validate(item))
                if len(rows) > 100_000:
                    raise RegistryError("Справочник превышает 100 000 каналов.")
            cursor = None if isinstance(data, list) else data.get("next_cursor")
            if not cursor:
                return rows
            if not isinstance(cursor, str) or len(cursor) > 1000 or cursor in cursors:
                raise RegistryError("Некорректная пагинация учётной системы.")
            cursors.add(cursor)
    raise RegistryError("Превышено 100 страниц учётной системы.")


def synchronize(session: Session, settings: Settings, actor: str = "system") -> IntegrationRun:
    if not settings.equipment_sync_enabled or not settings.equipment_sync_url:
        raise RegistryError("Подключение к учётной системе не настроено.")
    lock_registry(session)
    run = IntegrationRun(
        id=uuid4().hex,
        kind="equipment_sync",
        source=settings.equipment_sync_source,
        status="running",
    )
    session.add(run)
    session.flush()
    try:
        rows = fetch_registry(settings)
        counts = upsert(session, rows, settings.equipment_sync_source)
        queue_registry(session)
        run.status = "success"
        run.result = json.dumps({"accepted": len(rows), **counts})
        run.detail = "Реестр синхронизирован. Отсутствующие в ответе каналы не удаляются."
    except (httpx.HTTPError, OSError, ValueError, TypeError, AttributeError) as error:
        session.rollback()
        run = IntegrationRun(
            id=run.id,
            kind="equipment_sync",
            source=settings.equipment_sync_source,
            status="failed",
            detail=str(error)
            if isinstance(error, RegistryError)
            else "Не удалось получить корректный реестр. Проверьте адрес, TLS и формат ответа.",
        )
        session.add(run)
    run.finished_at = utcnow()
    audit.record(
        session,
        actor=actor,
        role="admin",
        action="equipment.sync",
        resource_type="integration_run",
        resource_id=run.id,
        detail=run.status,
    )
    session.commit()
    return run
