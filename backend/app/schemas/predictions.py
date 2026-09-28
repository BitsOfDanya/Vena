from datetime import datetime
from typing import Literal

from pydantic import BaseModel

RiskLevel = Literal["critical", "attention", "observe", "normal"]
ScoreType = Literal["risk_score", "calibrated_probability"]


class ModelInfo(BaseModel):
    model_id: str
    model_version: str | None = None
    horizon_hours: int | None = None
    calibrated: bool = False


class RiskFactor(BaseModel):
    key: str
    label: str
    value: float
    basis: Literal["feature_value"] = "feature_value"


class Driver(BaseModel):
    feature: str
    label: str
    value: float | None
    # Additive log-odds contribution to the model score (SHAP for trees).
    contribution: float


class Prediction(BaseModel):
    id: str
    asset_id: str
    device_type: str
    model_id: str
    model_version: str | None
    prediction_time: datetime
    horizon_hours: int | None
    score: float
    score_type: ScoreType
    risk_level: RiskLevel
    model_risk_level: str
    previous_score: float | None = None
    score_delta: float | None = None
    predicted_event_type: str
    scenario: str = "equipment"
    location_tag: str | None = None
    location_group: str | None = None
    location: str | None = None
    lead_time_hours: int | None = None
    factors: list[RiskFactor] = []
    drivers: list[Driver] = []
    sensor_type: str | None = None
    system_type: str | None = None
    last_event_at: datetime | None = None
    source_snapshot: str


class PredictionDetail(BaseModel):
    prediction: Prediction
    model: ModelInfo
    factors: list[RiskFactor]
    open_action_id: str | None = None
    notification_id: str | None = None


class StreamInfo(BaseModel):
    events: int
    channels_rescored: int
    received_at: datetime
    published_at: datetime
    # Seconds from the batch reaching the API to the snapshot being published.
    latency_seconds: float


class SnapshotStatus(BaseModel):
    available: bool
    snapshot_id: str | None = None
    prediction_time: datetime | None = None
    generated_at: datetime | None = None
    age_seconds: int | None = None
    stale: bool = False
    prediction_count: int = 0
    models: list[ModelInfo] = []
    stream: StreamInfo | None = None
    detail: str = ""


class AlarmAssessment(BaseModel):
    channel_id: str
    ts: datetime
    sensor_type: str
    # Calibrated probability that the alarm is confirmed within 30 minutes by a
    # repeat, a neighbouring channel or a sustained detection state.
    corroboration_probability: float
    needs_verification: bool
    location: str | None = None
    name: str | None = None


class AccessEvent(BaseModel):
    channel_id: str
    ts: datetime
    sensor_type: str
    object: str
    # Triage index for verification, not a probability of intrusion.
    access_index: float
    night: bool
    chain: bool
    location: str | None = None
    name: str | None = None


class FeedbackRow(BaseModel):
    prediction_id: str | None
    asset_id: str
    model_id: str | None
    prediction_time: datetime | None
    score: float | None
    horizon_hours: int | None
    action_id: str
    action_status: str
    action_result: str | None
    completed_at: datetime | None
