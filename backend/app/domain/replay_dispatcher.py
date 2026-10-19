import hashlib
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Action, Equipment, HistoricalEvent
from app.domain import actions as action_service

ACTOR = "Симуляция диспетчера"
CREWS = ("Бригада А", "Бригада Б", "Бригада В")
LEAVE_SHARE = 0.15
DISMISS_BY_SHARE = (("verified_normal", 0.7), ("monitoring", 0.9), ("false_alarm", 1.0))
TARGET_STATES = (
    ("smoke_alarm_", "Обнаружен дым"),
    ("pump_", "Неисправен"),
    ("fan_", "Неисправен"),
    ("smoke_", "Неисправен"),
    ("phase_", "Обесточен"),
    ("flood_", "Затоплен"),
)
CONFIRMED_NOTE = "Симуляция: событие в журнале через {hours} ч после прогноза"
DISMISSED_NOTE = "Симуляция: в горизонте прогноза событие не наступило"


def share(key: str) -> float:
    return int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def target_state(model_id: str) -> str | None:
    return next((state for prefix, state in TARGET_STATES if model_id.startswith(prefix)), None)


def wall_time(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def dismiss_reason(action_id: str) -> str:
    roll = share(action_id + "r")
    return next(name for name, edge in DISMISS_BY_SHARE if roll <= edge)


def _neighbours(session: Session, asset_id: str) -> list[str]:
    own = session.get(Equipment, asset_id)
    if own is None:
        return [asset_id]
    statement = select(Equipment.asset_id).where(
        Equipment.object_id == own.object_id, Equipment.equipment_type == own.equipment_type
    )
    return sorted({asset_id, *session.scalars(statement)})


def first_event(
    session: Session, channels: list[str], state: str, moment: datetime, hours: int, zone: ZoneInfo
) -> datetime | None:
    return session.scalar(
        select(func.min(HistoricalEvent.ts)).where(
            HistoricalEvent.channel_id.in_(channels),
            HistoricalEvent.value == state,
            HistoricalEvent.ts > moment.replace(tzinfo=zone),
            HistoricalEvent.ts <= (moment + timedelta(hours=hours)).replace(tzinfo=zone),
        )
    )


def simulate(session: Session, since: datetime, clock: datetime, timezone: str) -> dict[str, int]:
    zone = ZoneInfo(timezone)
    counts = {"confirmed": 0, "dismissed": 0, "left": 0}
    statement = (
        select(Action)
        .where(
            Action.source == "vena_forecast",
            Action.status == "suggested",
            Action.created_at >= since,
            Action.source_prediction_time.is_not(None),
        )
        .order_by(Action.created_at, Action.id)
    )
    for action in list(session.scalars(statement)):
        state = target_state(action.source_model_id or action.source_detail)
        if state is None or action.source_prediction_time is None:
            continue
        moment = wall_time(action.source_prediction_time)
        hours = action.source_horizon_hours or 24
        if moment + timedelta(hours=hours) > clock:
            continue
        if share(action.id) < LEAVE_SHARE:
            counts["left"] += 1
            continue
        happened = first_event(
            session, _neighbours(session, action.asset_id), state, moment, hours, zone
        )
        if happened is None:
            action_service.dismiss(
                session, action, dismiss_reason(action.id), DISMISSED_NOTE, ACTOR
            )
            counts["dismissed"] += 1
            continue
        lead = (happened.astimezone(zone).replace(tzinfo=None) - moment).total_seconds() / 3600
        model = action.source_model_id or ""
        outcome = (
            "maintenance_performed"
            if model.startswith(("pump_", "fan_")) and share(action.id + "o") < 0.5
            else "confirmed_issue"
        )
        action_service.approve(session, action, ACTOR)
        action_service.assign(
            session, action, CREWS[int(share(action.id + "c") * len(CREWS)) % len(CREWS)], ACTOR
        )
        action_service.transition(session, action, "in_progress", ACTOR)
        action_service.complete(
            session, action, outcome, CONFIRMED_NOTE.format(hours=max(round(lead), 1)), ACTOR
        )
        counts["confirmed"] += 1
    return counts
