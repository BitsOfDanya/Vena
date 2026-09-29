"""Asset tree for the network view and the effect report for management."""

import json
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain import journal as journal_service
from app.domain.health import load_calibration, location_health
from app.domain.incidents import LEVEL_RANK, group_incidents, location_label
from app.domain.predictions import PredictionSource
from app.schemas.analytics import (
    BacktestDay,
    ChannelNode,
    EffectReport,
    EventTypeStats,
    ForecastDay,
    ForecastTotal,
    ModelEffect,
    ObjectNode,
    SectionNode,
)
from app.schemas.predictions import Prediction

AVOIDED = {"false_or_irrelevant_signal", "no_issue_found"}


def _strongest(predictions: list[Prediction]) -> dict[str, Prediction]:
    best: dict[str, Prediction] = {}
    for prediction in predictions:
        current = best.get(prediction.asset_id)
        if current is None or (LEVEL_RANK[prediction.risk_level], -prediction.score) < (
            LEVEL_RANK[current.risk_level],
            -current.score,
        ):
            best[prediction.asset_id] = prediction
    return best


def asset_tree(source: PredictionSource) -> list[ObjectNode]:
    """Object → section → channel from the SMVU tags, with health and risks."""
    predictions = source.all()
    health = location_health(
        predictions, source.incident_probabilities(), load_calibration(source.settings.ml_dir)
    )
    sections: dict[str, list[Prediction]] = {}
    for prediction in _strongest(predictions).values():
        if prediction.location_group:
            sections.setdefault(prediction.location_group, []).append(prediction)
    objects: dict[str, list[SectionNode]] = {}
    for group, members in sections.items():
        members.sort(key=lambda item: (LEVEL_RANK[item.risk_level], -item.score))
        state = health.get(group)
        objects.setdefault(group.split("-", 1)[0], []).append(
            SectionNode(
                group=group,
                label=location_label(group),
                health_index=state.index if state else None,
                main_scenario=state.main_scenario if state else None,
                risk_by_scenario=state.risk_by_scenario if state else {},
                channels=[
                    ChannelNode(
                        asset_id=item.asset_id,
                        name=item.name,
                        sensor_type=item.sensor_type,
                        scenario=item.scenario,
                        model_id=item.model_id,
                        probability=item.score,
                        risk_level=item.risk_level,
                    )
                    for item in members
                ],
            )
        )
    result = []
    for object_id, nodes in objects.items():
        nodes.sort(key=lambda item: item.health_index if item.health_index is not None else 101)
        indexes = [item.health_index for item in nodes if item.health_index is not None]
        result.append(
            ObjectNode(
                object_id=object_id,
                label=f"Объект {object_id}",
                health_index=min(indexes) if indexes else None,
                sections=nodes,
            )
        )
    result.sort(key=lambda item: item.health_index if item.health_index is not None else 101)
    return result


def _read(path: Path) -> Any:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _lead_times(settings: Settings) -> list[ModelEffect]:
    result = []
    report = _read(settings.ml_dir / "results" / "model_report.json") or {}
    for model_id, item in report.items():
        point = (item.get("lead_time_2026h1") or {}).get("high")
        if point:
            result.append(
                ModelEffect(
                    model_id=model_id,
                    level="high",
                    episode_recall=point.get("episode_recall"),
                    alert_precision=point.get("alert_precision_dedup"),
                    median_lead_time_hours=point.get("median_lead_time_hours"),
                    alerts_per_day=point.get("alerts_per_day"),
                )
            )
    meta = _read(settings.ml_dir / "artifacts" / "models" / "phase_24h" / "meta.json") or {}
    point = meta.get("metrics_snapshot", {}).get("operating_point_precision_0.70")
    if point:
        result.insert(
            0,
            ModelEffect(
                model_id="phase_24h",
                level="precision 0.70",
                episode_recall=point.get("episode_recall"),
                alert_precision=point.get("alert_precision_dedup"),
                median_lead_time_hours=point.get("median_lead_time_hours"),
                alerts_per_day=point.get("alerts_per_day"),
            ),
        )
    return result


def effect(session: Session, settings: Settings, source: PredictionSource) -> EffectReport:
    significant = [item for item in source.all() if item.risk_level in ("critical", "attention")]
    alarms = source.alarms() if source.available else []
    alarm_meta = _read(settings.ml_dir / "artifacts" / "models" / "alarm_30m" / "meta.json") or {}
    operating = alarm_meta.get("metrics_snapshot", {}).get("operating_test", {})
    rows = journal_service.entries(session, settings, limit=100_000)
    summary = journal_service.summary(rows)
    return EffectReport(
        channels_at_risk=len({item.asset_id for item in significant}),
        incidents=len(group_incidents(_strongest(significant).values())),
        lead_time=_lead_times(settings),
        alarms_30d=len(alarms),
        alarms_to_verify=sum(1 for item in alarms if item.needs_verification),
        alarm_filter_share=operating.get("filtered_uncorroborated"),
        access_events_30d=len(source.access_events()) if source.available else 0,
        forecasts_in_journal=summary.total,
        decided=summary.decided,
        confirmed=sum(item.confirmed for item in summary.by_scenario),
        rejected=sum(item.rejected for item in summary.by_scenario),
        dispatches_avoided=sum(
            1 for row in rows if row.decision == "no_dispatch" and row.outcome in AVOIDED
        ),
        prospective=_read(settings.ml_dir / "results" / "predictions" / "prospective.json"),
    )


# Incident types of the seasonal analytics: the ML key, title, scenario and the
# models that forecast the type channel by channel.
EVENT_TYPES = (
    ("pump_fault", "Отказ насоса", "flooding", ("pump_24h", "pump_72h")),
    ("flooding", "Затопление камеры", "flooding", ("flood_24h",)),
    ("ventilation_fault", "Отказ вентилятора", "ventilation", ("fan_24h", "fan_72h")),
    ("smoke_sensor_fault", "Неисправность дымового датчика", "fire", ("smoke_24h",)),
    ("smoke_detected", "Срабатывание дымового датчика", "fire", ("smoke_alarm_24h",)),
    ("power_loss", "Потеря питания", "power_loss", ("phase_24h",)),
)


def event_types(settings: Settings, source: PredictionSource) -> list[EventTypeStats]:
    """Current risk, past volume, seasonal profile and 14-day forecast per incident type."""
    seasonality = _read(settings.ml_dir / "results" / "seasonality.json") or {}
    workload = (_read(settings.ml_dir / "results" / "workload_forecast.json") or {}).get(
        "scenarios", {}
    )
    predictions = source.all() if source.available else []
    result = []
    for key, title, scenario, models in EVENT_TYPES:
        at_risk: dict[str, set[str]] = {}
        for item in predictions:
            if item.model_id in models and item.risk_level in ("critical", "attention"):
                at_risk.setdefault(item.risk_level, set()).add(item.asset_id)
        forecast = workload.get(key, {})
        recent = forecast.get("recent", {})
        history = forecast.get("history", {})
        method = forecast.get("method")
        week = forecast.get("next_7_days")
        monthly = seasonality.get("monthly_onsets_per_100_channels", {}).get(key, {})
        result.append(
            EventTypeStats(
                event_type=key,
                title=title,
                scenario=scenario,
                models=list(models),
                channels_at_risk={level: len(ids) for level, ids in at_risk.items()},
                episodes_30d=history.get("last_30_days"),
                episodes_365d=history.get("last_365_days"),
                monthly_per_100_channels={str(month): value for month, value in monthly.items()},
                forecast_method=method,
                forecast=[ForecastDay(**day) for day in forecast.get("forecast", [])],
                next_7_days=ForecastTotal(**week) if week else None,
                week_error=(recent.get(method) or {}).get("week") if method else None,
                week_error_baseline=(recent.get("last_28_days") or {}).get("week"),
                backtest=[BacktestDay(**day) for day in forecast.get("backtest", [])],
            )
        )
    return result
