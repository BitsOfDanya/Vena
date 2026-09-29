from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Equipment, HistoricalEvent, ImportOutbox, SmvuIngestState, utcnow
from app.domain.equipment import RegistryError, lock_registry


def get_status(session: Session) -> dict:
    state = session.get(SmvuIngestState, "default")
    if state is None or state.received_at is None:
        return {
            "configured": False,
            "last_batch_id": None,
            "last_event_count": 0,
            "last_event_at": None,
            "received_at": None,
            "age_seconds": None,
            "fresh": False,
            "detail": "Пакеты событий СМВУ ещё не поступали",
        }
    age = int((utcnow() - state.received_at).total_seconds())
    return {
        "configured": True,
        "last_batch_id": state.last_batch_id or None,
        "last_event_count": state.last_event_count,
        "last_event_at": state.last_event_at,
        "received_at": state.received_at,
        "age_seconds": age,
        "fresh": age <= 300,
        "detail": state.detail or "",
    }


def spool_events(
    inbox: Path, batch_id: str, events: list[dict], timezone: str, delivery_id: str | None = None
) -> datetime:
    zone = ZoneInfo(timezone)
    inbox.mkdir(parents=True, exist_ok=True)
    name = f"{utcnow():%Y%m%dT%H%M%S%f}-{batch_id}.jsonl"
    if delivery_id:
        name = f"stream-{delivery_id}.jsonl"
    temporary = inbox / f".{name}.tmp"
    latest: datetime | None = None
    with temporary.open("w", encoding="utf-8") as handle:
        for event in events:
            ts = event["ts"]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is not None:
                ts = ts.astimezone(zone).replace(tzinfo=None)
            latest = ts if latest is None else max(latest, ts)
            record = {**event, "ts": ts.isoformat()}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temporary, inbox / name)
    assert latest is not None
    return latest


def queue_events(
    session: Session, events: list[dict], batch_id: str, timezone: str
) -> tuple[datetime, int]:
    lock_registry(session)
    known = set(session.scalars(select(Equipment.asset_id)))
    seen: dict[str, dict] = {}
    for event in events:
        values = dict(event)
        if values["ts"].tzinfo is None:
            values["ts"] = values["ts"].replace(tzinfo=ZoneInfo(timezone))
        if known and values["channel_id"] not in known:
            raise RegistryError("Канал отсутствует в реестре: сначала обновите справочник")
        key = values["event_id"]
        if key in seen and seen[key] != values:
            raise RegistryError("Повторный идентификатор события с другими значениями")
        seen[key] = values
    latest = max(row["ts"] for row in seen.values())
    rows = list(seen.values())
    added = []
    for offset in range(0, len(rows), 1000):
        batch = rows[offset : offset + 1000]
        existing = {
            row.event_id: row
            for row in session.scalars(
                select(HistoricalEvent).where(
                    HistoricalEvent.event_id.in_([row["event_id"] for row in batch])
                )
            )
        }
        for row in batch:
            current = existing.get(row["event_id"])
            if current:
                if any(getattr(current, key) != value for key, value in row.items()):
                    raise RegistryError("Событие уже записано с другими значениями")
                continue
            session.add(HistoricalEvent(**row))
            added.append({**row, "ts": row["ts"].isoformat()})
        session.flush()
    if added:
        session.add(
            ImportOutbox(
                id=uuid4().hex,
                payload=json.dumps(
                    {"kind": "stream", "batch_id": batch_id, "events": added}, ensure_ascii=False
                ),
            )
        )
    return latest, len(added)


def accept_batch(
    session: Session,
    *,
    batch_id: str,
    event_count: int,
    last_event_at: datetime | None,
    detail: str = "",
) -> dict:
    state = session.get(SmvuIngestState, "default")
    if state is None:
        state = SmvuIngestState(id="default")
        session.add(state)
    state.last_batch_id = batch_id
    state.last_event_count = event_count
    if last_event_at is not None and last_event_at.tzinfo is None:
        last_event_at = last_event_at.replace(tzinfo=UTC)
    state.last_event_at = last_event_at
    state.received_at = utcnow()
    state.detail = detail
    session.flush()
    return get_status(session)
