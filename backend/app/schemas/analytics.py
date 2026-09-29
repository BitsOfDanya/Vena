from typing import Any

from pydantic import BaseModel


class ChannelNode(BaseModel):
    asset_id: str
    name: str | None
    sensor_type: str | None
    scenario: str
    model_id: str
    probability: float
    risk_level: str


class SectionNode(BaseModel):
    group: str
    label: str | None
    health_index: int | None
    main_scenario: str | None
    risk_by_scenario: dict[str, float]
    channels: list[ChannelNode]


class ObjectNode(BaseModel):
    object_id: str
    label: str
    health_index: int | None
    sections: list[SectionNode]


class ModelEffect(BaseModel):
    model_id: str
    level: str
    episode_recall: float | None
    alert_precision: float | None
    median_lead_time_hours: float | None
    alerts_per_day: float | None


class EffectReport(BaseModel):
    channels_at_risk: int
    incidents: int
    lead_time: list[ModelEffect]
    alarms_30d: int
    alarms_to_verify: int
    alarms_maintenance: int
    alarm_filter_share: float | None
    access_events_30d: int
    forecasts_in_journal: int
    decided: int
    confirmed: int
    rejected: int
    dispatches_avoided: int
    prospective: dict[str, Any] | None


class ForecastDay(BaseModel):
    day: str
    expected: float


class ForecastTotal(BaseModel):
    expected: float
    low: float
    high: float


class BacktestDay(BaseModel):
    day: str
    actual: int
    forecast: float


class EventTypeStats(BaseModel):
    event_type: str
    title: str
    scenario: str
    models: list[str]
    channels_at_risk: dict[str, int]
    episodes_30d: int | None
    episodes_365d: int | None
    monthly_per_100_channels: dict[str, float]
    forecast_method: str | None
    forecast: list[ForecastDay]
    next_7_days: ForecastTotal | None
    week_error: float | None
    week_error_baseline: float | None
    backtest: list[BacktestDay]
