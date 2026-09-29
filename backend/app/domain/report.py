"""Management report as an XLSX workbook (ТЗ, section 8)."""

import csv
from datetime import datetime
from io import BytesIO, StringIO
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain import analytics
from app.domain import journal as journal_service
from app.domain import system as system_service
from app.domain.incidents import SCENARIO_LABELS, reason_text
from app.domain.predictions import PredictionSource
from app.schemas.predictions import Prediction

DECISIONS = {
    "awaiting_decision": "Ожидает решения",
    "crew_dispatched": "Выезд бригады",
    "no_dispatch": "Без выезда",
    "completed": "Отработано",
    "cancelled": "Отменено",
}


def _sheet(workbook: Workbook, title: str, header: list[str], rows: list[list[Any]]) -> None:
    sheet = workbook.create_sheet(title)
    sheet.append(header)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    for column in sheet.columns:
        width = max(len(str(cell.value or "")) for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 70)
    sheet.freeze_panes = "A2"


def _percent(value: float | None) -> str:
    return "" if value is None else f"{value:.0%}"


def management_report(session: Session, settings: Settings, source: PredictionSource) -> bytes:
    effect = analytics.effect(session, settings, source)
    workbook = Workbook()
    if workbook.active is not None:
        workbook.remove(workbook.active)
    _sheet(
        workbook,
        "Сводка",
        ["Показатель", "Значение"],
        [
            ["Каналов с высоким риском", effect.channels_at_risk],
            ["Инцидентов после группировки", effect.incidents],
            ["Тревог за 30 дней", effect.alarms_30d],
            ["Тревог на проверку перед выездом", effect.alarms_to_verify],
            ["Отсеивается неподтверждающихся тревог", _percent(effect.alarm_filter_share)],
            ["Событий доступа на проверку за 30 дней", effect.access_events_30d],
            ["Прогнозов в журнале", effect.forecasts_in_journal],
            ["Решений диспетчера", effect.decided],
            ["Подтверждено", effect.confirmed],
            ["Отклонено", effect.rejected],
            ["Выездов не потребовалось", effect.dispatches_avoided],
        ],
    )
    _sheet(
        workbook,
        "Модели",
        [
            "Модель",
            "Уровень",
            "Предупреждено эпизодов",
            "Точность тревог",
            "Упреждение, ч",
            "Тревог в сутки",
        ],
        [
            [
                item.model_id,
                item.level,
                _percent(item.episode_recall),
                _percent(item.alert_precision),
                item.median_lead_time_hours,
                item.alerts_per_day,
            ]
            for item in effect.lead_time
        ],
    )
    situations = system_service.situations(session, settings, limit=200)
    _sheet(
        workbook,
        "Инциденты",
        [
            "Инцидент",
            "Критичность",
            "Каналов",
            "Вероятность",
            "Индекс здоровья",
            "Причина",
            "Что делать",
            "Статус",
        ],
        [
            [
                item.title,
                item.severity,
                item.asset_count,
                _percent(item.risk_score),
                item.health_index,
                item.primary_reason,
                item.recommendation.title if item.recommendation else "",
                item.status,
            ]
            for item in situations
        ],
    )
    significant = [p for p in source.all() if p.risk_level in ("critical", "attention")]
    significant.sort(key=lambda item: -item.score)
    _sheet(
        workbook,
        "Прогнозы",
        [
            "Канал",
            "Название",
            "Локация",
            "Сценарий",
            "Модель",
            "Вероятность",
            "Горизонт, ч",
            "Уровень",
            "Причина",
        ],
        [
            [
                item.asset_id,
                item.name or "",
                item.location or "",
                SCENARIO_LABELS.get(item.scenario, item.scenario),
                item.model_id,
                _percent(item.score),
                item.horizon_hours,
                item.risk_level,
                reason_text(item),
            ]
            for item in significant
        ],
    )
    _sheet(
        workbook,
        "Журнал",
        [
            "Работа",
            "Создана",
            "Канал",
            "Локация",
            "Сценарий",
            "Модель",
            "Вероятность",
            "Решение",
            "Исход",
            "Примечание",
        ],
        [
            [
                row.id,
                row.created_at.replace(tzinfo=None),
                row.asset_id,
                row.location or "",
                SCENARIO_LABELS.get(row.scenario, row.scenario),
                row.model_id or "",
                _percent(row.score),
                DECISIONS.get(row.decision, row.decision),
                row.outcome or "",
                row.result_note,
            ]
            for row in journal_service.entries(session, settings, limit=100_000)
        ],
    )
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


EXPORT_FIELDS = (
    "id",
    "asset_id",
    "name",
    "sensor_type",
    "location_tag",
    "location_group",
    "scenario",
    "model_id",
    "horizon_hours",
    "score",
    "score_type",
    "risk_level",
    "prediction_time",
)


def _export_value(prediction: Prediction, field: str) -> str:
    value = getattr(prediction, field)
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def predictions_csv(predictions: list[Prediction]) -> bytes:
    """Forecasts as CSV for file exchange (ТЗ, section 7)."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_FIELDS)
    for prediction in predictions:
        writer.writerow([_export_value(prediction, field) for field in EXPORT_FIELDS])
    return buffer.getvalue().encode("utf-8-sig")


def predictions_xml(predictions: list[Prediction], snapshot: str | None) -> bytes:
    """Forecasts as XML for systems that exchange XML (ТЗ, section 7)."""
    root = Element("predictions", {"snapshot": snapshot or "", "count": str(len(predictions))})
    for prediction in predictions:
        node = SubElement(root, "prediction")
        for field in EXPORT_FIELDS:
            SubElement(node, field).text = _export_value(prediction, field)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
