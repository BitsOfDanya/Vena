from __future__ import annotations

from datetime import UTC, datetime

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
