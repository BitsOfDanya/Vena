"""Management report as an XLSX workbook (ТЗ, section 8)."""

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain import analytics
from app.domain import journal as journal_service
from app.domain import system as system_service
from app.domain.incidents import SCENARIO_LABELS, reason_text
from app.domain.predictions import PredictionSource

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
