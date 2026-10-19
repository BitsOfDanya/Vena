import json
import math
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import Settings
from app.domain.hierarchy import load as load_hierarchy
from app.domain.incidents import object_label
from app.domain.predictions import get_prediction_source
from app.domain.scopes import Scope
from app.schemas.incidents import (
    IncidentKind,
    IncidentKindSummary,
    IncidentRecord,
    IncidentRegistry,
    ObjectCount,
    ObjectHistory,
    ObjectModelMeta,
    ObjectNowcastMeta,
    ObjectRisk,
    ObjectRiskList,
    YearCount,
)

REGISTRY_FILE = "incident_registry.json"
KINDS = ("power", "flood", "fire")
KIND_LABELS = {"power": "Отключение питания объекта", "flood": "Подтопление", "fire": "Пожар"}
SCENARIOS = ("power_loss", "flooding", "fire")
SCENARIO_LABELS = {"power_loss": "Питание", "flooding": "Подтопление", "fire": "Пожар"}
HISTORY_KEYS = {"1d": "events_1d", "7d": "events_7d", "30d": "events_30d", "90d": "events_90d"}
REGISTRY_MISSING = "Реестр инцидентов ещё не рассчитан"
RECENT_MISSING = "Список последних инцидентов ещё не рассчитан"
OBJECTS_MISSING = "Утренний список объектов ещё не рассчитан"


def _float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _int(value: Any) -> int | None:
    number = _float(value)
    return int(number) if number is not None else None


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _object(value: Any) -> str | None:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, int | str) and not isinstance(value, bool):
        text = str(value).strip()
        return text or None
    return None


def _zone(settings: Settings) -> ZoneInfo:
    try:
        return ZoneInfo(settings.timezone)
    except (ValueError, ZoneInfoNotFoundError):
        return ZoneInfo("UTC")


def _time(value: Any, zone: ZoneInfo) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict[str, Any] | None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def read_registry(settings: Settings) -> dict[str, Any] | None:
    path = settings.ml_dir / "results" / REGISTRY_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return _load(str(path), mtime)


def _per_year(raw: Any) -> list[YearCount]:
    pairs = raw.items() if isinstance(raw, dict) else []
    result = [
        YearCount(year=str(year), count=count)
        for year, value in pairs
        if (count := _int(value)) is not None
    ]
    return sorted(result, key=lambda item: item.year)


def _top_objects(raw: Any, scope: Scope) -> list[ObjectCount]:
    result = []
    for key, value in raw.items() if isinstance(raw, dict) else []:
        object_id, count = _object(key), _int(value)
        if object_id is None or count is None or not scope.has_object(object_id):
            continue
        result.append(
            ObjectCount(object_id=object_id, object_name=object_label(object_id) or "", count=count)
        )
    return sorted(result, key=lambda item: (-item.count, item.object_id))


def _summary(kind: str, raw: dict[str, Any], scope: Scope) -> IncidentKindSummary:
    return IncidentKindSummary(
        kind=cast(IncidentKind, kind),
        label=_text(raw.get("label")) or KIND_LABELS[kind],
        rule=_text(raw.get("rule")),
        total=_int(raw.get("total")) or 0,
        objects=_int(raw.get("objects")) or 0,
        per_year=_per_year(raw.get("per_year")),
        recent_2026h1=_int(raw.get("recent_2026h1")),
        per_day_2026h1=_float(raw.get("per_day_2026h1")),
        channels_median=_float(raw.get("channels_median")),
        top_objects=_top_objects(raw.get("top_objects"), scope),
        temperature_confirmed=_int(raw.get("temperature_confirmed")),
        long_over_30_minutes=_int(raw.get("long_over_30_minutes")),
    )


def _record(row: Any, labels: dict[str, str], zone: ZoneInfo) -> IncidentRecord | None:
    if not isinstance(row, dict):
        return None
    kind = row.get("kind")
    object_id = _object(row.get("object"))
    start = _time(row.get("start"), zone)
    if kind not in KIND_LABELS or object_id is None or start is None:
        return None
    confirmed = row.get("temperature_confirmed")
    return IncidentRecord(
        kind=kind,
        label=labels.get(kind) or KIND_LABELS[kind],
        object_id=object_id,
        object_name=object_label(object_id) or "",
        start=start,
        end=_time(row.get("end"), zone),
        channels=_int(row.get("channels")),
        temperature_confirmed=confirmed if isinstance(confirmed, bool) else None,
        max_minutes=_float(row.get("max_minutes")),
    )


def registry(
    settings: Settings, scope: Scope, kind: str | None = None, limit: int = 300
) -> IncidentRegistry:
    restricted = not scope.unrestricted
    data = read_registry(settings) or {}
    incidents = data.get("incidents")
    if not isinstance(incidents, dict):
        return IncidentRegistry(available=False, detail=REGISTRY_MISSING, restricted=restricted)
    load_hierarchy(settings)
    kinds = [
        _summary(key, incidents[key], scope)
        for key in KINDS
        if isinstance(incidents.get(key), dict)
    ]
    labels: dict[str, str] = {item.kind: item.label for item in kinds}
    journal_end = _text(data.get("journal_end")) or None
    raw_recent = data.get("recent")
    if not isinstance(raw_recent, list):
        return IncidentRegistry(
            available=True,
            detail=RECENT_MISSING,
            journal_end=journal_end,
            restricted=restricted,
            kinds=kinds,
        )
    zone = _zone(settings)
    records = [
        record
        for row in raw_recent
        if (record := _record(row, labels, zone)) is not None
        and scope.has_object(record.object_id)
        and (kind is None or record.kind == kind)
    ]
    records.sort(key=lambda item: item.start, reverse=True)
    return IncidentRegistry(
        available=True,
        journal_end=journal_end,
        restricted=restricted,
        kinds=kinds,
        recent=records[:limit],
    )


def _nowcast(raw: Any) -> ObjectNowcastMeta | None:
    if not isinstance(raw, dict):
        return None
    model_id, horizon = _text(raw.get("model_id")), _int(raw.get("horizon_hours"))
    if not model_id or horizon is None:
        return None
    return ObjectNowcastMeta(
        model_id=model_id,
        horizon_hours=horizon,
        period=_text(raw.get("period")) or None,
        share_top3=_float(raw.get("share_top3")),
        rule_share_top3=_float(raw.get("rule_share_top3")),
        objects=_int(raw.get("objects")),
    )


def _meta(model_id: str, raw: dict[str, Any]) -> ObjectModelMeta:
    scenario = _text(raw.get("scenario"))
    return ObjectModelMeta(
        model_id=model_id,
        label=_text(raw.get("label")) or SCENARIO_LABELS.get(scenario, model_id),
        scenario=scenario,
        precision_top3=_float(raw.get("precision_top3")),
        recall_top3=_float(raw.get("recall_top3")),
        base_rate=_float(raw.get("base_rate")),
        avg_precision=_float(raw.get("avg_precision")),
        period=_text(raw.get("period")) or None,
        rule=_text(raw.get("rule")),
        nowcast=_nowcast(raw.get("nowcast")),
    )


def _history(raw: Any) -> ObjectHistory:
    if not isinstance(raw, dict):
        return ObjectHistory()
    values: dict[str, Any] = {field: _int(raw.get(key)) for key, field in HISTORY_KEYS.items()}
    values["days_since"] = _float(raw.get("days_since"))
    return ObjectHistory(**values)


def _risk(row: dict[str, Any], models: dict[str, ObjectModelMeta]) -> ObjectRisk | None:
    object_id = _object(row.get("object_id"))
    model_id = _text(row.get("model_id"))
    probability, rank = _float(row.get("probability")), _int(row.get("rank"))
    if object_id is None or probability is None or rank is None:
        return None
    meta = models.get(model_id)
    scenario = _text(row.get("scenario")) or (meta.scenario if meta else "")
    if not scenario:
        return None
    return ObjectRisk(
        object_id=object_id,
        object_name=object_label(object_id) or "",
        scenario=scenario,
        model_id=model_id,
        model_label=meta.label if meta else SCENARIO_LABELS.get(scenario, scenario),
        probability=probability,
        rank=rank,
        horizon_hours=_int(row.get("horizon_hours")),
        history=_history(row.get("history")),
        channel_score=_float(row.get("channel_score")),
        probability_6h=_float(row.get("probability_6h")),
    )


def _scenario_order(scenario: str) -> tuple[int, str]:
    return (SCENARIOS.index(scenario) if scenario in SCENARIOS else len(SCENARIOS), scenario)


def object_risks(
    settings: Settings, scope: Scope, scenario: str | None = None, limit: int = 100
) -> ObjectRiskList:
    restricted = not scope.unrestricted
    source = get_prediction_source(settings)
    if not source.available:
        return ObjectRiskList(available=False, detail=OBJECTS_MISSING, restricted=restricted)
    rows, raw_meta = source.object_risks()
    if not rows:
        return ObjectRiskList(available=False, detail=OBJECTS_MISSING, restricted=restricted)
    load_hierarchy(settings)
    models = {model_id: _meta(model_id, raw) for model_id, raw in raw_meta.items()}
    items = [
        item
        for row in rows
        if (item := _risk(row, models)) is not None
        and scope.has_object(item.object_id)
        and (not scenario or item.scenario == scenario)
    ]
    items.sort(key=lambda item: (_scenario_order(item.scenario), item.rank, item.object_id))
    counts: dict[str, int] = {}
    limited = []
    for item in items:
        counts[item.scenario] = counts.get(item.scenario, 0) + 1
        if counts[item.scenario] <= limit:
            limited.append(item)
    meta = [item for item in models.values() if not scenario or item.scenario == scenario]
    meta.sort(key=lambda item: (_scenario_order(item.scenario), item.model_id))
    return ObjectRiskList(
        available=True,
        prediction_time=source.status().prediction_time,
        restricted=restricted,
        models=meta,
        items=limited,
    )
