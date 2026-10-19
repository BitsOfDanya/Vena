from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, Field

Text = Annotated[str, BeforeValidator(lambda value: "" if value is None else str(value))]

ReplayStatus = Literal["idle", "preparing", "running", "stopping", "finished", "failed"]


class ScenarioLead(BaseModel):
    hours_before: float
    place: int
    objects_ranked: int


class ScenarioItem(BaseModel):
    id: Text = Field(min_length=1)
    kind: Text = ""
    label: Text = ""
    object: Text = Field(min_length=1)
    start: datetime
    end: datetime
    channels: int = 0
    rule: Text = ""
    before_hours: float = Field(default=24, ge=0, le=168)
    after_hours: float = Field(default=2, ge=0, le=48)
    lead: list[ScenarioLead] = []


class ScenarioCatalog(BaseModel):
    generated_at: str | None = None
    note: Text = ""
    summary: dict[str, dict[str, Any]] = {}
    items: list[ScenarioItem] = []


class ReplaySimulation(BaseModel):
    confirmed: int = 0
    dismissed: int = 0
    left: int = 0


class ReplayScenarioState(BaseModel):
    id: str
    kind: str = ""
    label: str = ""
    object: str = ""
    stage: str | None = None
    stage_index: int = 0
    stages: int = 0
    shift_days: int = 0
    replay_date: datetime | None = None


class ReplayState(BaseModel):
    state: ReplayStatus = "idle"
    mode: Literal["week", "scenario"] | None = None
    active: bool = False
    live: bool = True
    start: datetime | None = None
    end: datetime | None = None
    clock: datetime | None = None
    speed: float | None = None
    sent_events: int = 0
    batches: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    detail: str = ""
    simulate_dispatcher: bool = False
    simulation: ReplaySimulation = ReplaySimulation()
    scenario: ReplayScenarioState | None = None
    ml_history_end: datetime | None = None
    ml_clock: datetime | None = None
    journal_from: datetime | None = None
    journal_to: datetime | None = None


class ReplayWeekIn(BaseModel):
    start: datetime
    end: datetime
    speed: float = Field(default=2160, ge=60, le=17280)
    simulate_dispatcher: bool = True


class ReplayScenarioIn(BaseModel):
    id: str = Field(min_length=1, max_length=120)


class ReplayStopIn(BaseModel):
    return_live: bool = False
