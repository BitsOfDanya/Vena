from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Action, ActionEvent
from app.schemas.actions import ActionCreate, ActionPatch

OPEN_STATUSES = ("suggested", "planned", "assigned", "in_progress", "waiting")

TRANSITIONS: dict[str, set[str]] = {
    "suggested": {"planned", "dismissed", "cancelled"},
    "planned": {"assigned", "in_progress", "cancelled"},
    "assigned": {"in_progress", "waiting", "cancelled"},
    "in_progress": {"waiting", "completed", "cancelled"},
    "waiting": {"in_progress", "completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
    "dismissed": set(),
}

EVENT_FOR_STATUS = {
    "planned": "planned",
    "assigned": "assigned",
    "in_progress": "started",
    "waiting": "waiting",
    "completed": "completed",
    "cancelled": "cancelled",
    "dismissed": "dismissed",
}


class InvalidTransition(Exception):
    pass


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _next_id(session: Session) -> str:
    last = session.scalars(select(Action.id).order_by(Action.id.desc()).limit(1)).first()
    number = (
        int(last.split("-")[1]) + 1
        if last and last.startswith("A-") and last.split("-")[1].isdigit()
        else 1101
    )
    return f"A-{number}"


def record(
    session: Session,
    action: Action,
    event_type: str,
    actor: str,
    note: str = "",
    to_status: str | None = None,
) -> None:
    session.add(
        ActionEvent(
            action_id=action.id,
            event_type=event_type,
            actor=actor,
            at=_now(),
            from_status=action.status if to_status else None,
            to_status=to_status,
            note=note,
        )
    )


def list_actions(
    session: Session, status: str | None = None, asset_id: str | None = None
) -> list[Action]:
    statement = select(Action).options(selectinload(Action.history)).order_by(Action.recommended_at)
    if status:
        statement = statement.where(Action.status == status)
    if asset_id:
        statement = statement.where(Action.asset_id == asset_id)
    return list(session.scalars(statement))


def get_action(session: Session, action_id: str) -> Action | None:
    return session.get(Action, action_id)


def create_action(session: Session, payload: ActionCreate, actor: str) -> Action:
    now = _now()
    action = Action(
        id=_next_id(session),
        asset_id=payload.asset_id,
        source=payload.source,
        source_detail=payload.source_detail,
        source_pattern_id=payload.source_pattern_id,
        kind=payload.kind,
        reason=payload.reason,
        priority=payload.priority,
        window_start=now,
        recommended_at=payload.recommended_at,
        status=payload.status,
        assignee=payload.assignee,
        note=payload.note,
        notify_channels=",".join(payload.notify_channels),
        created_by=actor,
        created_at=now,
        updated_at=now,
        source_prediction_id=payload.source_prediction_id,
        source_model_id=payload.source_model_id,
        source_prediction_time=payload.source_prediction_time,
        source_score=payload.source_score,
        source_horizon_hours=payload.source_horizon_hours,
    )
    session.add(action)
    session.flush()
    record(
        session,
        action,
        "suggested" if payload.status == "suggested" else "created",
        actor,
        payload.source_detail,
    )
    if payload.notify_channels:
        record(session, action, "notification_requested", actor, ",".join(payload.notify_channels))
    session.flush()
    return action


def patch_action(session: Session, action: Action, patch: ActionPatch, actor: str) -> Action:
    for field, value in patch.model_dump(exclude_none=True).items():
        setattr(action, field, value)
    action.updated_at = _now()
    record(session, action, "updated", actor)
    session.flush()
    return action


def transition(
    session: Session, action: Action, to_status: str, actor: str, note: str = ""
) -> Action:
    if to_status not in TRANSITIONS[action.status]:
        raise InvalidTransition(f"{action.status} -> {to_status}")
    record(session, action, EVENT_FOR_STATUS[to_status], actor, note, to_status=to_status)
    action.status = to_status
    action.updated_at = _now()
    session.flush()
    return action


def approve(session: Session, action: Action, actor: str) -> Action:
    if action.status != "suggested":
        raise InvalidTransition(f"{action.status} -> planned")
    record(session, action, "approved", actor, to_status="planned")
    action.status = "planned"
    action.updated_at = _now()
    session.flush()
    return action


def assign(session: Session, action: Action, assignee: str, actor: str) -> Action:
    action.assignee = assignee
    return transition(session, action, "assigned", actor, assignee)


def complete(session: Session, action: Action, outcome: str, note: str, actor: str) -> Action:
    if action.status in {"completed", "cancelled", "dismissed"}:
        raise InvalidTransition(f"{action.status} -> completed")
    now = _now()
    record(session, action, "completed", actor, note, to_status="completed")
    action.status = "completed"
    action.result_outcome = outcome
    action.result_note = note
    action.completed_at = now
    action.updated_at = now
    record(session, action, "result_recorded", actor, outcome)
    session.flush()
    return action


DISMISS_REASONS: dict[str, tuple[str, str]] = {
    "false_alarm": ("Ложное срабатывание", "false_or_irrelevant_signal"),
    "planned_works": ("Плановые работы на объекте", "false_or_irrelevant_signal"),
    "verified_normal": ("Проверено по камерам и телеметрии: норма", "no_issue_found"),
    "monitoring": ("Мониторинг ситуации без выезда", "monitoring_required"),
    "duplicate": ("Дубль уже открытой работы", "other"),
    "other": ("Другое", "other"),
}


def dismiss(session: Session, action: Action, reason: str, note: str, actor: str) -> Action:
    label, outcome = DISMISS_REASONS[reason]
    detail = f"{label}. {note}".strip() if note else label
    updated = transition(session, action, "dismissed", actor, detail)
    updated.result_outcome = outcome
    updated.result_note = detail
    updated.completed_at = _now()
    session.flush()
    return updated


def to_dict(action: Action) -> dict:
    return {
        "id": action.id,
        "asset_id": action.asset_id,
        "source": action.source,
        "source_detail": action.source_detail,
        "source_pattern_id": action.source_pattern_id,
        "kind": action.kind,
        "reason": action.reason,
        "priority": action.priority,
        "window_start": action.window_start,
        "recommended_at": action.recommended_at,
        "status": action.status,
        "assignee": action.assignee,
        "note": action.note,
        "notify_channels": [item for item in action.notify_channels.split(",") if item],
        "created_by": action.created_by,
        "created_at": action.created_at,
        "updated_at": action.updated_at,
        "source_prediction_id": action.source_prediction_id,
        "source_model_id": action.source_model_id,
        "source_prediction_time": action.source_prediction_time,
        "source_score": action.source_score,
        "source_horizon_hours": action.source_horizon_hours,
        "result_outcome": action.result_outcome,
        "result_note": action.result_note,
        "completed_at": action.completed_at,
        "history": action.history,
    }
