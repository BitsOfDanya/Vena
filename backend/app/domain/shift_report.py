from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action
from app.domain import journal_tail
from app.domain.actions import OPEN_STATUSES
from app.domain.incidents import LEVEL_RANK, group_incidents, location_label, reason_text
from app.domain.predictions import PredictionSource
from app.domain.recommendations import driver_hints
from app.schemas.predictions import Prediction

TOP = 10
EVENT_LIMIT = 500
KINDS = {
    "неисправен": "fault",
    "обесточен": "power",
    "отключено устройство": "power",
    "затоплен": "flood",
    "обнаружен дым": "smoke",
}


def _predicted(source: PredictionSource, hints: dict[str, str]) -> dict[str, Any]:
    if not source.available:
        return {
            "available": False,
            "prediction_time": None,
            "total": 0,
            "levels": {},
            "scenarios": {},
            "incidents": 0,
            "top": [],
        }
    items = source.all()
    levels = Counter(item.risk_level for item in items)
    risky = [item for item in items if item.risk_level in ("critical", "attention")]
    scenarios = Counter(item.scenario for item in risky)
    risky.sort(key=lambda item: (LEVEL_RANK[item.risk_level], -item.score))
    queues: dict[str, list[Prediction]] = {}
    for item in risky:
        queues.setdefault(item.scenario, []).append(item)
    top: list[Prediction] = []
    while len(top) < TOP and any(queues.values()):
        for queue in queues.values():
            if queue and len(top) < TOP:
                top.append(queue.pop(0))
    status = source.status()
    return {
        "available": True,
        "prediction_time": status.prediction_time,
        "total": len(items),
        "levels": dict(levels),
        "scenarios": dict(scenarios),
        "incidents": sum(1 for incident in group_incidents(risky)),
        "top": [
            {
                "asset_id": item.asset_id,
                "name": item.name,
                "location": location_label(item.location_group),
                "scenario": item.scenario,
                "model_id": item.model_id,
                "probability": item.score,
                "horizon_hours": item.horizon_hours,
                "risk_level": item.risk_level,
                "reason": reason_text(item, hints),
            }
            for item in top
        ],
    }


def _happened(settings: Settings, hours: int) -> dict[str, Any]:
    if settings.dataset_dir is None or not settings.dataset_dir.is_dir():
        return {
            "available": False,
            "from": None,
            "to": None,
            "total": 0,
            "kinds": {},
            "objects": [],
            "latest": [],
        }
    feed = journal_tail.recent(settings.dataset_dir, hours, EVENT_LIMIT, None, settings.timezone)
    items = feed["items"]
    kinds = Counter(
        KINDS.get(item["value"].strip().lower(), "alarm" if item["alarm"] else "state")
        for item in items
    )
    objects = Counter(item["object_id"] for item in items if item["object_id"])
    return {
        "available": bool(items) or feed["latest_at"] is not None,
        "from": feed["from"],
        "to": feed["latest_at"],
        "total": len(items),
        "truncated": feed["has_more"],
        "kinds": dict(kinds),
        "objects": [{"object_id": key, "events": value} for key, value in objects.most_common(5)],
        "latest": items[:12],
    }


def _done(session: Session, start: datetime, now: datetime) -> dict[str, Any]:
    touched = list(
        session.scalars(
            select(Action).where(
                or_(
                    Action.created_at >= start,
                    Action.completed_at >= start,
                    Action.updated_at >= start,
                )
            )
        )
    )
    created = [action for action in touched if action.created_at >= start]
    completed = [
        action
        for action in touched
        if action.completed_at is not None and action.completed_at >= start
    ]
    open_now = list(session.scalars(select(Action).where(Action.status.in_(OPEN_STATUSES))))
    overdue = [
        action
        for action in open_now
        if action.recommended_at < now and action.status != "suggested"
    ]
    outcomes = Counter(action.result_outcome or "без исхода" for action in completed)
    return {
        "created": len(created),
        "from_models": sum(1 for action in created if action.source_model_id),
        "completed": len(completed),
        "open": len(open_now),
        "overdue": len(overdue),
        "outcomes": dict(outcomes),
        "completed_items": [
            {
                "asset_id": action.asset_id,
                "reason": action.reason,
                "outcome": action.result_outcome,
                "note": action.result_note,
                "completed_at": action.completed_at,
            }
            for action in sorted(
                completed, key=lambda action: action.completed_at or now, reverse=True
            )[:TOP]
        ],
    }


def shift_report(
    session: Session, settings: Settings, source: PredictionSource, hours: int, now: datetime
) -> dict[str, Any]:
    start = now - timedelta(hours=hours)
    return {
        "generated_at": now,
        "hours": hours,
        "from": start,
        "to": now,
        "predicted": _predicted(source, driver_hints(settings)),
        "happened": _happened(settings, hours),
        "done": _done(session, start, now),
    }
