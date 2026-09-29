from datetime import datetime

from pydantic import BaseModel


class JournalEntry(BaseModel):
    id: str
    created_at: datetime
    asset_id: str
    location: str | None
    scenario: str
    model_id: str | None
    score: float | None
    horizon_hours: int | None
    prediction_time: datetime | None
    priority: str
    status: str
    decision: str
    outcome: str | None
    result_note: str
    assignee: str
    completed_at: datetime | None


class ScenarioFeedback(BaseModel):
    scenario: str
    forecasts: int
    decided: int
    confirmed: int
    rejected: int
    confirmation_rate: float | None


class JournalSummary(BaseModel):
    total: int
    pending: int
    in_work: int
    decided: int
    by_scenario: list[ScenarioFeedback]


class DecisionReason(BaseModel):
    code: str
    label: str
    outcome: str
