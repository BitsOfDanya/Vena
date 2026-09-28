from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActionStatus = Literal[
    "suggested",
    "planned",
    "assigned",
    "in_progress",
    "waiting",
    "completed",
    "cancelled",
    "dismissed",
]
ActionSource = Literal["vena_forecast", "manual", "external_request"]
ActionPriority = Literal["high", "medium", "low"]
ActionOutcome = Literal[
    "confirmed_issue",
    "no_issue_found",
    "maintenance_performed",
    "monitoring_required",
    "false_or_irrelevant_signal",
    "other",
]


class ActionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    actor: str
    at: datetime
    from_status: str | None
    to_status: str | None
    note: str


class ActionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_id: str
    source: ActionSource
    source_detail: str
    source_pattern_id: str | None
    kind: str
    reason: str
    priority: ActionPriority
    window_start: datetime
    recommended_at: datetime
    status: ActionStatus
    assignee: str
    note: str
    notify_channels: list[str] = []
    created_by: str
    created_at: datetime
    updated_at: datetime
    source_prediction_id: str | None = None
    source_model_id: str | None = None
    source_prediction_time: datetime | None = None
    source_score: float | None = None
    source_horizon_hours: int | None = None
    result_outcome: ActionOutcome | None
    result_note: str
    completed_at: datetime | None
    history: list[ActionEventOut] = []


class ActionCreate(BaseModel):
    asset_id: str = Field(min_length=1, max_length=32)
    kind: str = "inspect"
    reason: str = ""
    priority: ActionPriority = "medium"
    recommended_at: datetime
    assignee: str = ""
    note: str = ""
    source: ActionSource = "manual"
    source_detail: str = ""
    source_pattern_id: str | None = None
    notify_channels: list[Literal["in_app", "email"]] = []
    status: Literal["suggested", "planned"] = "planned"
    source_prediction_id: str | None = None
    source_model_id: str | None = None
    source_prediction_time: datetime | None = None
    source_score: float | None = None
    source_horizon_hours: int | None = None


class ActionPatch(BaseModel):
    reason: str | None = None
    priority: ActionPriority | None = None
    recommended_at: datetime | None = None
    assignee: str | None = None
    note: str | None = None


class AssignRequest(BaseModel):
    assignee: str = Field(min_length=1, max_length=120)
    notify: bool = False


DismissReason = Literal[
    "false_alarm", "planned_works", "verified_normal", "monitoring", "duplicate", "other"
]


class DismissRequest(BaseModel):
    reason: DismissReason = "false_alarm"
    note: str = Field(default="", max_length=500)


class ResultRequest(BaseModel):
    outcome: ActionOutcome
    note: str = ""
