import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.domain.incidents import (
    LEVEL_RANK,
    location_group,
    location_label,
    scenario_for,
)
from app.schemas.predictions import (
    AccessEvent,
    AlarmAssessment,
    ModelInfo,
    Prediction,
    RiskFactor,
    RiskLevel,
    SnapshotStatus,
)

SNAPSHOT_NAME = "snapshot.json"

FACTOR_LABELS = {
    "events_24h": "Events, 24h",
    "events_7d": "Events, 7d",
    "alarms_24h": "Alarms, 24h",
    "failures_30d": "Failures, 30d",
    "time_since_last_failure_days": "Days since last failure",
}

# Model configs carry thresholds for critical/high/medium; anything below is normal.
# The mapping is presentation only and never changes the raw model score.
LEVEL_MAP: dict[str, RiskLevel] = {
    "critical": "critical",
    "high": "attention",
    "medium": "observe",
    "low": "normal",
}


class SnapshotUnavailable(Exception):
    pass


def snapshot_path(settings: Settings) -> Path:
    return settings.ml_dir / "results" / "predictions" / SNAPSHOT_NAME


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _factors(raw: dict[str, Any]) -> list[RiskFactor]:
    factors = []
    for key, value in raw.items():
        if not isinstance(value, int | float):
            continue
        factors.append(RiskFactor(key=key, label=FACTOR_LABELS.get(key, key), value=float(value)))
    return factors


class PredictionSource:
    """Reads the read-only prediction snapshot produced by the ML pipeline."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._snapshot_id: str | None = None
        self._loaded_mtime: float | None = None
        self._payload: dict[str, Any] | None = None
        self._predictions: list[Prediction] = []
        self._error: str = ""

    def _read(self) -> None:
        path = snapshot_path(self._settings)
        if not path.is_file():
            self._payload = None
            self._predictions = []
            self._error = "prediction snapshot is not available"
            return
        mtime = path.stat().st_mtime
        if self._loaded_mtime == mtime and self._payload is not None:
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            self._payload = None
            self._predictions = []
            self._error = f"prediction snapshot is unreadable: {error}"
            return
        self._payload = payload
        self._loaded_mtime = mtime
        self._error = ""
        self._predictions = self._map(payload)

    def _map(self, payload: dict[str, Any]) -> list[Prediction]:
        snapshot_id = str(payload.get("snapshot_id", ""))
        prediction_time = _parse_time(payload.get("prediction_time")) or datetime.now(tz=UTC)
        result: list[Prediction] = []
        for row in payload.get("predictions", []):
            try:
                asset_id = str(row["channel_id"])
                model_id = str(row["model_id"])
                score = float(row["score"])
            except (KeyError, TypeError, ValueError):
                continue
            model_level = str(row.get("model_risk_level", "low"))
            score_type = row.get("score_type", "risk_score")
            device_type = str(row.get("device_type", ""))
            scenario = str(row.get("scenario") or scenario_for(device_type, model_id))
            tag = row.get("tag") if isinstance(row.get("tag"), str) else None
            group = location_group(tag)
            result.append(
                Prediction(
                    id=f"{snapshot_id}:{model_id}:{asset_id}",
                    asset_id=asset_id,
                    device_type=device_type,
                    model_id=model_id,
                    model_version=row.get("model_version"),
                    prediction_time=prediction_time,
                    horizon_hours=row.get("horizon_hours"),
                    score=score,
                    score_type="calibrated_probability"
                    if score_type == "calibrated_probability"
                    else "risk_score",
                    risk_level=LEVEL_MAP.get(model_level, "normal"),
                    model_risk_level=model_level,
                    predicted_event_type=scenario,
                    scenario=scenario,
                    location_tag=tag,
                    location_group=group,
                    location=location_label(group),
                    lead_time_hours=row.get("horizon_hours"),
                    factors=_factors(row.get("factors", {})),
                    sensor_type=row.get("sensor_type"),
                    system_type=row.get("system_type"),
                    last_event_at=_parse_time(row.get("last_event_at")),
                    source_snapshot=snapshot_id,
                )
            )
        return result

    @property
    def available(self) -> bool:
        self._read()
        return self._payload is not None

    def status(self) -> SnapshotStatus:
        self._read()
        if self._payload is None:
            return SnapshotStatus(available=False, detail=self._error)
        generated_at = _parse_time(self._payload.get("generated_at"))
        prediction_time = _parse_time(self._payload.get("prediction_time"))
        reference = prediction_time or generated_at
        age = int((datetime.now(tz=UTC) - reference).total_seconds()) if reference else None
        models = [
            ModelInfo(
                model_id=name,
                model_version=info.get("version"),
                horizon_hours=info.get("horizon_hours"),
                calibrated=bool(info.get("calibrated", False)),
            )
            for name, info in (self._payload.get("models") or {}).items()
        ]
        return SnapshotStatus(
            available=True,
            snapshot_id=str(self._payload.get("snapshot_id", "")),
            prediction_time=prediction_time,
            generated_at=generated_at,
            age_seconds=age,
            stale=age is not None and age > self._settings.prediction_stale_seconds,
            prediction_count=len(self._predictions),
            models=models,
        )

    def all(self) -> list[Prediction]:
        self._read()
        return list(self._predictions)

    def query(
        self,
        asset_id: str | None = None,
        device_type: str | None = None,
        risk_level: str | None = None,
        horizon: int | None = None,
        model_id: str | None = None,
        sort: str = "risk_desc",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Prediction]:
        items = self.all()
        if asset_id:
            items = [item for item in items if item.asset_id == asset_id]
        if device_type:
            items = [item for item in items if item.device_type == device_type]
        if risk_level:
            items = [item for item in items if item.risk_level == risk_level]
        if horizon:
            items = [item for item in items if item.horizon_hours == horizon]
        if model_id:
            items = [item for item in items if item.model_id == model_id]
        if sort == "delta_desc":
            items.sort(key=lambda item: item.score_delta or 0, reverse=True)
        elif sort == "latest":
            items.sort(key=lambda item: item.prediction_time, reverse=True)
        else:
            # Scores of different models are not on one scale, so the model's own
            # risk level orders first and the score only breaks ties inside a level.
            items.sort(key=lambda item: (LEVEL_RANK[item.risk_level], -item.score))
        return items[offset : offset + limit]

    def _section(self, key: str) -> list[dict[str, Any]]:
        self._read()
        rows = (self._payload or {}).get(key) or []
        return [row for row in rows if isinstance(row, dict)]

    def alarms(self) -> list[AlarmAssessment]:
        result = []
        for row in self._section("alarms"):
            group = location_group(row.get("tag"))
            result.append(AlarmAssessment(**row, location=location_label(group)))
        result.sort(key=lambda item: item.ts, reverse=True)
        return result

    def access_events(self) -> list[AccessEvent]:
        result = []
        for row in self._section("access_events"):
            group = location_group(row.get("tag"))
            result.append(AccessEvent(**row, location=location_label(group)))
        result.sort(key=lambda item: (-item.access_index, item.ts))
        return result

    def get(self, prediction_id: str) -> Prediction | None:
        return next((item for item in self.all() if item.id == prediction_id), None)

    def latest_for_asset(self, asset_id: str) -> Prediction | None:
        items = [item for item in self.all() if item.asset_id == asset_id]
        if not items:
            return None
        return max(items, key=lambda item: (item.horizon_hours or 0, item.score))


_source: PredictionSource | None = None


def get_prediction_source(settings: Settings) -> PredictionSource:
    global _source
    if _source is None:
        _source = PredictionSource(settings)
    return _source


def reset_prediction_source() -> None:
    global _source
    _source = None
