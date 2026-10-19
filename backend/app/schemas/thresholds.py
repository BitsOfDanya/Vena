from pydantic import BaseModel, Field, model_validator


class ThresholdLevels(BaseModel):
    critical: float
    high: float
    medium: float


class ThresholdUpdate(ThresholdLevels):
    critical: float = Field(gt=0, le=1)
    high: float = Field(gt=0, le=1)
    medium: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def ordered(self) -> "ThresholdUpdate":
        if not self.critical >= self.high >= self.medium:
            raise ValueError("Пороги должны идти по убыванию: критично ≥ внимание ≥ наблюдение")
        return self


class CurvePoint(BaseModel):
    threshold: float
    probability: float | None = None
    precision: float | None = None
    recall: float | None = None
    channels_per_day: float | None = None


class ModelThresholds(BaseModel):
    model_id: str
    label: str
    horizon_hours: int | None = None
    period: str | None = None
    base_rate: float | None = None
    default: ThresholdLevels | None = None
    override: ThresholdLevels | None = None
    effective: ThresholdLevels | None = None
    current: dict[str, CurvePoint] = {}
    curve: list[CurvePoint] = []
