import json
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import SettingsRecord
from app.db.session import SessionLocal
from app.schemas.predictions import ModelInfo
from app.schemas.thresholds import CurvePoint, ModelThresholds, ThresholdLevels

SETTINGS_KEY = "model_thresholds"
CURVES_NAME = "threshold_curves.json"
LEVELS = ("critical", "high", "medium")
REFRESH_SECONDS = 5.0

LABELS = {
    "pump_24h": "Неисправность насоса",
    "pump_72h": "Неисправность насоса",
    "fan_24h": "Неисправность вентилятора",
    "fan_72h": "Неисправность вентилятора",
    "smoke_24h": "Неисправность датчика дыма",
    "smoke_alarm_24h": "Срабатывание датчика дыма",
    "phase_24h": "Потеря питания",
    "flood_24h": "Затопление камеры",
}

Levels = dict[str, float]

_version = ""
_overrides: dict[str, Levels] = {}
_checked = float("-inf")


def model_level(raw_score: float, thresholds: Levels) -> str:
    for level in LEVELS:
        if raw_score >= thresholds[level]:
            return level
    return "low"


def parse_levels(raw: Any) -> Levels | None:
    if not isinstance(raw, dict):
        return None
    try:
        return {level: float(raw[level]) for level in LEVELS}
    except (KeyError, TypeError, ValueError):
        return None


def _parse(value: str | None) -> dict[str, Levels]:
    if not value:
        return {}
    try:
        raw = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    parsed = {str(model_id): parse_levels(levels) for model_id, levels in raw.items()}
    return {model_id: levels for model_id, levels in parsed.items() if levels}


def stored(session: Session) -> dict[str, Levels]:
    record = session.get(SettingsRecord, SETTINGS_KEY)
    return _parse(record.value if record else None)


def save(session: Session, model_id: str, levels: Levels | None) -> None:
    overrides = stored(session)
    if levels is None:
        overrides.pop(model_id, None)
    else:
        overrides[model_id] = levels
    value = json.dumps(overrides, sort_keys=True)
    record = session.get(SettingsRecord, SETTINGS_KEY)
    if record is None:
        session.add(SettingsRecord(key=SETTINGS_KEY, value=value))
    else:
        record.value = value
    session.flush()


def current() -> tuple[str, dict[str, Levels]]:
    global _version, _overrides, _checked
    now = time.monotonic()
    if now - _checked < REFRESH_SECONDS:
        return _version, _overrides
    try:
        with SessionLocal() as session:
            value = session.scalar(
                select(SettingsRecord.value).where(SettingsRecord.key == SETTINGS_KEY)
            )
    except SQLAlchemyError:
        _checked = now
        return _version, _overrides
    _version, _overrides, _checked = value or "", _parse(value), now
    return _version, _overrides


def invalidate() -> None:
    global _checked
    _checked = float("-inf")


def load_curves(settings: Settings) -> dict[str, Any]:
    path = settings.ml_dir / "results" / CURVES_NAME
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, dict):
        return {}
    return {"period": payload.get("period"), "models": models}


def _point(raw: Any) -> CurvePoint | None:
    if not isinstance(raw, dict):
        return None
    try:
        return CurvePoint(**raw)
    except (TypeError, ValueError):
        return None


def _curve(raw: Any) -> list[CurvePoint]:
    points = [_point(item) for item in raw] if isinstance(raw, list) else []
    return sorted((point for point in points if point), key=lambda point: point.threshold)


def catalogue(
    session: Session,
    settings: Settings,
    models: list[ModelInfo],
    defaults: dict[str, Levels],
) -> list[ModelThresholds]:
    curves = load_curves(settings)
    curve_models: dict[str, Any] = curves.get("models", {})
    overrides = stored(session)
    horizons = {model.model_id: model.horizon_hours for model in models}
    result = []
    for model_id in dict.fromkeys([*horizons, *defaults, *curve_models]):
        info = curve_models.get(model_id)
        info = info if isinstance(info, dict) else {}
        raw_current = info.get("current")
        points = {
            level: point
            for level in LEVELS
            if isinstance(raw_current, dict) and (point := _point(raw_current.get(level)))
        }
        default = defaults.get(model_id) or (
            {level: points[level].threshold for level in LEVELS}
            if len(points) == len(LEVELS)
            else None
        )
        override = overrides.get(model_id)
        effective = override or default
        horizon = horizons.get(model_id) or info.get("horizon_hours")
        base_rate = info.get("base_rate")
        period = curves.get("period") if info else None
        result.append(
            ModelThresholds(
                model_id=model_id,
                label=str(info.get("label") or LABELS.get(model_id, model_id)),
                horizon_hours=horizon if isinstance(horizon, int) else None,
                period=str(period) if period else None,
                base_rate=base_rate if isinstance(base_rate, int | float) else None,
                default=ThresholdLevels(**default) if default else None,
                override=ThresholdLevels(**override) if override else None,
                effective=ThresholdLevels(**effective) if effective else None,
                current=points,
                curve=_curve(info.get("curve")),
            )
        )
    return result
