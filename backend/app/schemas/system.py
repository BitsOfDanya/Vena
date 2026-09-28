from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SystemNotice(BaseModel):
    id: str
    kind: Literal["data_delayed", "api_unavailable", "model_unavailable", "integration_failure"]
    severity: Literal["info", "attention", "critical"]
    title: str
    description: str
    href: str | None = None
    dismissible: bool = True


class HealthComponents(BaseModel):
    api: str
    ml: str
    data: str
    spatial: str
    notification_service: str
    last_prediction_at: datetime | None = None
    last_event_at: datetime | None = None


class Situation(BaseModel):
    id: str
    type: Literal["risk", "pattern", "action"]
    severity: Literal["critical", "attention"]
    title: str
    summary: str
    asset_ids: list[str]
    pattern_id: str | None
    risk_score: float | None
    risk_delta: float | None
    forecast_horizon: int | None
    primary_reason: str
    status: Literal["new", "acknowledged", "action_created", "resolved"]
    updated_at: datetime
    open_action_id: str | None
    notification_id: str | None
    scenario: str | None = None
    location: str | None = None
    asset_count: int = 1
