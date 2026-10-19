from datetime import datetime
from typing import Literal

from pydantic import BaseModel

IncidentKind = Literal["fire", "flood", "power"]


class YearCount(BaseModel):
    year: str
    count: int


class ObjectCount(BaseModel):
    object_id: str
    object_name: str
    count: int


class IncidentKindSummary(BaseModel):
    kind: IncidentKind
    label: str
    rule: str = ""
    total: int = 0
    objects: int = 0
    per_year: list[YearCount] = []
    recent_2026h1: int | None = None
    per_day_2026h1: float | None = None
    channels_median: float | None = None
    top_objects: list[ObjectCount] = []
    temperature_confirmed: int | None = None
    long_over_30_minutes: int | None = None


class IncidentRecord(BaseModel):
    kind: IncidentKind
    label: str
    object_id: str
    object_name: str
    start: datetime
    end: datetime | None = None
    channels: int | None = None
    temperature_confirmed: bool | None = None
    max_minutes: float | None = None


class IncidentRegistry(BaseModel):
    available: bool
    detail: str = ""
    journal_end: str | None = None
    restricted: bool = False
    kinds: list[IncidentKindSummary] = []
    recent: list[IncidentRecord] = []


class ObjectHistory(BaseModel):
    events_1d: int | None = None
    events_7d: int | None = None
    events_30d: int | None = None
    events_90d: int | None = None
    days_since: float | None = None


class ObjectNowcastMeta(BaseModel):
    model_id: str
    horizon_hours: int
    period: str | None = None
    share_top3: float | None = None
    rule_share_top3: float | None = None
    objects: int | None = None


class ObjectModelMeta(BaseModel):
    model_id: str
    label: str
    scenario: str
    precision_top3: float | None = None
    recall_top3: float | None = None
    base_rate: float | None = None
    avg_precision: float | None = None
    period: str | None = None
    rule: str = ""
    nowcast: ObjectNowcastMeta | None = None


class ObjectRisk(BaseModel):
    object_id: str
    object_name: str
    scenario: str
    model_id: str
    model_label: str
    probability: float
    rank: int
    horizon_hours: int | None = None
    history: ObjectHistory = ObjectHistory()
    channel_score: float | None = None
    probability_6h: float | None = None


class ObjectRiskList(BaseModel):
    available: bool
    detail: str = ""
    prediction_time: datetime | None = None
    restricted: bool = False
    models: list[ObjectModelMeta] = []
    items: list[ObjectRisk] = []
