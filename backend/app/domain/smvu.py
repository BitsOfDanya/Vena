from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import SmvuIngestState, utcnow


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
            "detail": "No SMVU batches received yet",
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


def spool_events(inbox: Path, batch_id: str, events: list[dict], timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    inbox.mkdir(parents=True, exist_ok=True)
    name = f"{utcnow():%Y%m%dT%H%M%S%f}-{batch_id}.jsonl"
    temporary = inbox / f".{name}.tmp"
    latest: datetime | None = None
    with temporary.open("w", encoding="utf-8") as handle:
        for event in events:
            ts: datetime = event["ts"]
            if ts.tzinfo is not None:
                ts = ts.astimezone(zone).replace(tzinfo=None)
            latest = ts if latest is None else max(latest, ts)
            record = {**event, "ts": ts.isoformat()}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(temporary, inbox / name)
    assert latest is not None
    return latest


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
