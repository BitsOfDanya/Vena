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


class Recommendation(BaseModel):
    title: str
    actions: list[str]
    # Reason-specific hint from the main driver of the lead forecast.
    hint: str | None = None
    note: str


class LocationHistory(BaseModel):
    episodes_365d: int
    channels: int
    last_episode_at: datetime
    median_duration_minutes: float


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
    # Calibrated probability that at least one channel of the location loses
    # power within 24 hours; only the power-loss scenario has a location model.
    incident_probability: float | None = None
    health_index: int | None = None
    recommendation: Recommendation | None = None
    history: LocationHistory | None = None
