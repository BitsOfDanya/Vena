"""Forecast journal: every forecast that reached the dispatcher and its handling.

The journal is the register required by the ТЗ (section 10): the forecast, the
dispatcher decision with its catalogue reason, and the crew result. Decided rows
are the labelled feedback exported for retraining.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action
from app.domain.incidents import location_label, scenario_for
from app.domain.predictions import get_prediction_source
from app.schemas.journal import JournalEntry, JournalSummary, ScenarioFeedback

CONFIRMED = {"confirmed_issue", "maintenance_performed"}
REJECTED = {"false_or_irrelevant_signal", "no_issue_found"}
IN_WORK = {"planned", "assigned", "in_progress", "waiting"}


def _decision(status: str) -> str:
    if status == "suggested":
        return "awaiting_decision"
    if status in IN_WORK:
        return "crew_dispatched"
    if status == "dismissed":
        return "no_dispatch"
    if status == "completed":
        return "completed"
    return "cancelled"


def entries(
    session: Session,
    settings: Settings,
    scenario: str | None = None,
    decision: str | None = None,
    limit: int = 500,
) -> list[JournalEntry]:
    source = get_prediction_source(settings)
    locations = {
        prediction.asset_id: prediction.location_group
        for prediction in (source.all() if source.available else [])
    }
    statement = (
        select(Action).where(Action.source == "vena_forecast").order_by(Action.created_at.desc())
    )
    result: list[JournalEntry] = []
    for action in session.scalars(statement):
        model_id = action.source_model_id or action.source_detail or None
        entry = JournalEntry(
            id=action.id,
            created_at=action.created_at,
            asset_id=action.asset_id,
            location=location_label(locations.get(action.asset_id)),
            scenario=scenario_for("", model_id or ""),
            model_id=model_id,
            score=action.source_score,
            horizon_hours=action.source_horizon_hours,
            prediction_time=action.source_prediction_time,
            priority=action.priority,
            status=action.status,
            decision=_decision(action.status),
            outcome=action.result_outcome,
            result_note=action.result_note or "",
            assignee=action.assignee or "",
            completed_at=action.completed_at,
        )
        if scenario and entry.scenario != scenario:
            continue
        if decision and entry.decision != decision:
            continue
        result.append(entry)
        if len(result) >= limit:
            break
    return result


def summary(rows: list[JournalEntry]) -> JournalSummary:
    scenarios: dict[str, list[JournalEntry]] = {}
    for row in rows:
        scenarios.setdefault(row.scenario, []).append(row)
    feedback = []
    for scenario, items in sorted(scenarios.items()):
        confirmed = sum(1 for item in items if item.outcome in CONFIRMED)
        rejected = sum(1 for item in items if item.outcome in REJECTED)
        decided = sum(1 for item in items if item.outcome is not None)
        feedback.append(
            ScenarioFeedback(
                scenario=scenario,
                forecasts=len(items),
                decided=decided,
                confirmed=confirmed,
                rejected=rejected,
                confirmation_rate=round(confirmed / (confirmed + rejected), 3)
                if confirmed + rejected
                else None,
            )
        )
    return JournalSummary(
        total=len(rows),
        pending=sum(1 for row in rows if row.decision == "awaiting_decision"),
        in_work=sum(1 for row in rows if row.decision == "crew_dispatched"),
        decided=sum(1 for row in rows if row.outcome is not None),
        by_scenario=feedback,
    )
