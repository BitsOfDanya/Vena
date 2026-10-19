from collections.abc import Sequence
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.domain.incidents import LEVEL_LABELS, SCENARIO_LABELS
from app.domain.predictions import PredictionSource
from app.domain.report import OUTCOMES, Section, management_sections
from app.domain.scopes import EVERYTHING, Scope

FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
REGULAR = "PlexSans"
BOLD = "PlexSans-SemiBold"
PAGE = landscape(A4)
MARGIN = 14 * mm
WIDTH = PAGE[0] - 2 * MARGIN
INK = colors.HexColor("#1d2433")
MUTED = colors.HexColor("#5b6475")
ACCENT = colors.HexColor("#1f4e79")
LINE = colors.HexColor("#d5dbe5")
HEAD = colors.HexColor("#eef2f7")
STRIPE = colors.HexColor("#f8fafc")
LIMITS = {"Инциденты": 50, "Прогнозы": 100, "Журнал": 100}
KINDS = {
    "fault": "Неисправность",
    "power": "Обесточивание",
    "flood": "Затопление",
    "smoke": "Дым",
    "alarm": "Тревога",
    "state": "Смена состояния",
}


def _fonts() -> None:
    if REGULAR in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(REGULAR, str(FONTS / "PlexSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(BOLD, str(FONTS / "PlexSans-SemiBold.ttf")))
    pdfmetrics.registerFontFamily(
        REGULAR, normal=REGULAR, bold=BOLD, italic=REGULAR, boldItalic=BOLD
    )


def _style(
    name: str, size: float, font: str = REGULAR, color: Any = INK, **extra: Any
) -> ParagraphStyle:
    return ParagraphStyle(
        name, fontName=font, fontSize=size, leading=size * 1.3, textColor=color, **extra
    )


TITLE = _style("title", 18, BOLD, ACCENT, spaceAfter=2 * mm)
SUBTITLE = _style("subtitle", 10, color=MUTED, spaceAfter=1 * mm)
HEADING = _style("heading", 12, BOLD, spaceBefore=5 * mm, spaceAfter=2 * mm, keepWithNext=1)
CELL = _style("cell", 8)
CELL_HEAD = _style("cell-head", 8, BOLD)
NOTE = _style("note", 8, color=MUTED, spaceBefore=1 * mm)
KPI_VALUE = _style("kpi-value", 15, BOLD, ACCENT)
KPI_LABEL = _style("kpi-label", 7.5, color=MUTED)


def _local(value: datetime | None, zone: ZoneInfo) -> str:
    if value is None:
        return "—"
    aware = value if value.tzinfo else value.replace(tzinfo=UTC)
    return aware.astimezone(zone).strftime("%d.%m.%Y %H:%M")


def _zone_label(name: str) -> str:
    return "МСК" if name == "Europe/Moscow" else name


def _text(value: Any, zone: ZoneInfo) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        digits = 0 if abs(value) >= 100 else 1 if abs(value) >= 10 else 2
        shown = f"{value:.{digits}f}"
        return (shown.rstrip("0").rstrip(".") if "." in shown else shown).replace(".", ",")
    if isinstance(value, datetime):
        return _local(value, zone)
    return str(value)


class Report:
    def __init__(self, title: str, lines: Sequence[str], settings: Settings) -> None:
        _fonts()
        self.title = title
        self.zone = ZoneInfo(settings.timezone)
        self.generated = datetime.now(tz=UTC)
        self.story: list[Any] = [Paragraph(escape(title), TITLE)]
        self.story.extend(Paragraph(escape(line), SUBTITLE) for line in lines)

    def _cell(self, value: Any, style: ParagraphStyle = CELL) -> Paragraph:
        return Paragraph(escape(_text(value, self.zone)), style)

    def heading(self, text: str) -> None:
        self.story.append(Paragraph(escape(text), HEADING))

    def note(self, text: str) -> None:
        self.story.append(Paragraph(escape(text), NOTE))

    def kpis(self, items: Sequence[tuple[str, Any]], columns: int = 4) -> None:
        cells: list[Any] = [
            [self._cell(value, KPI_VALUE), Paragraph(escape(label), KPI_LABEL)]
            for label, value in items
        ]
        rows = [cells[index : index + columns] for index in range(0, len(cells), columns)]
        rows[-1] = rows[-1] + [""] * (columns - len(rows[-1]))
        table = Table(rows, colWidths=[WIDTH / columns] * columns)
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                    ("INNERGRID", (0, 0), (-1, -1), 0.6, LINE),
                    ("BACKGROUND", (0, 0), (-1, -1), STRIPE),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        self.story.append(table)

    def table(
        self,
        header: Sequence[str],
        rows: Sequence[Sequence[Any]],
        widths: Sequence[float],
        empty: str = "Нет данных",
    ) -> None:
        if not rows:
            self.story.append(Paragraph(escape(empty), NOTE))
            return
        scale = WIDTH / sum(widths)
        data = [[self._cell(item, CELL_HEAD) for item in header]]
        data.extend([self._cell(item) for item in row] for row in rows)
        table = Table(data, colWidths=[width * scale for width in widths], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), HEAD),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, ACCENT),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        self.story.append(table)

    def section(self, section: Section, widths: Sequence[float]) -> None:
        limit = LIMITS.get(section.title)
        rows = section.rows[:limit] if limit else section.rows
        self.heading(section.title)
        self.table(section.header, rows, widths)
        if limit and len(section.rows) > limit:
            self.note(
                f"Показаны первые {limit} из {len(section.rows)}. "
                "Полный список — в выгрузке management.xlsx."
            )

    def _decorate(self, canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN, 10 * mm, PAGE[0] - MARGIN, 10 * mm)
        canvas.setFont(REGULAR, 7.5)
        canvas.setFillColor(MUTED)
        stamp = _local(self.generated, self.zone)
        zone = _zone_label(self.zone.key)
        canvas.drawString(MARGIN, 6.5 * mm, f"VENA · {self.title} · сформирован {stamp} {zone}")
        canvas.drawRightString(PAGE[0] - MARGIN, 6.5 * mm, f"Стр. {document.page}")
        canvas.restoreState()

    def render(self) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=PAGE,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=MARGIN,
            bottomMargin=16 * mm,
            title=self.title,
            author="VENA",
            subject=self.title,
        )
        document.build(self.story, onFirstPage=self._decorate, onLaterPages=self._decorate)
        return buffer.getvalue()


WIDTHS = {
    "Модели": [75, 30, 42, 34, 30, 30],
    "Инциденты": [50, 22, 17, 21, 19, 55, 55, 30],
    "Прогнозы": [16, 40, 40, 25, 27, 21, 19, 18, 63],
    "Журнал": [15, 20, 16, 36, 25, 26, 21, 24, 30, 56],
}


def management_pdf(
    session: Session, settings: Settings, source: PredictionSource, scope: Scope = EVERYTHING
) -> bytes:
    sections = management_sections(session, settings, source, scope)
    zone, label = ZoneInfo(settings.timezone), _zone_label(settings.timezone)
    status = source.status()
    journal = next(section for section in sections if section.title == "Журнал")
    dates = [row[1] for row in journal.rows if isinstance(row[1], datetime)]
    period = (
        f"Период журнала решений: {_local(min(dates), zone)[:10]} — "
        f"{_local(datetime.now(tz=UTC), zone)[:10]}"
        if dates
        else "Журнал решений пока пуст"
    )
    report = Report(
        "Отчёт для руководства",
        [
            f"Снимок прогнозов: {_local(status.prediction_time, zone)} {label}"
            f" · прогнозов в снимке: {status.prediction_count}",
            period,
        ],
        settings,
    )
    report.story.append(Spacer(1, 2 * mm))
    report.heading("Ключевые показатели")
    report.kpis([(str(row[0]), row[1]) for row in sections[0].rows])
    for section in sections[1:]:
        report.section(section, WIDTHS[section.title])
    return report.render()


def _scenario(value: Any) -> str:
    return SCENARIO_LABELS.get(str(value), str(value))


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value):.0%}"


def shift_pdf(report_data: dict[str, Any], settings: Settings) -> bytes:
    zone = ZoneInfo(settings.timezone)
    label = _zone_label(settings.timezone)
    hours = report_data["hours"]
    report = Report(
        "Сводка за смену",
        [
            f"Период: {_local(report_data['from'], zone)} — {_local(report_data['to'], zone)} "
            f"{label}, {hours} ч"
        ],
        settings,
    )
    predicted, happened, done = (
        report_data["predicted"],
        report_data["happened"],
        report_data["done"],
    )
    levels = predicted.get("levels", {})
    report.heading("Ключевые показатели")
    report.kpis(
        [
            ("Прогнозов в снимке", predicted.get("total", 0)),
            ("Критично", levels.get("critical", 0)),
            ("Внимание", levels.get("attention", 0)),
            ("Инцидентов после группировки", predicted.get("incidents", 0)),
            ("Событий за смену", happened.get("total", 0)),
            ("Создано работ", done.get("created", 0)),
            ("Из них по прогнозам", done.get("from_models", 0)),
            ("Завершено работ", done.get("completed", 0)),
            ("Открыто сейчас", done.get("open", 0)),
            ("Просрочено", done.get("overdue", 0)),
        ],
        columns=5,
    )

    report.heading("Что прогнозируется")
    if not predicted.get("available"):
        report.note("Снимок прогнозов недоступен.")
    else:
        report.note(f"Снимок прогнозов: {_local(predicted.get('prediction_time'), zone)} {label}")
        report.table(
            [
                "Канал",
                "Название",
                "Локация",
                "Сценарий",
                "Вероятность",
                "Горизонт, ч",
                "Уровень",
                "Причина",
            ],
            [
                [
                    item["asset_id"],
                    item.get("name"),
                    item.get("location"),
                    _scenario(item.get("scenario")),
                    _percent(item.get("probability")),
                    item.get("horizon_hours"),
                    LEVEL_LABELS.get(item.get("risk_level"), item.get("risk_level")),
                    item.get("reason"),
                ]
                for item in predicted.get("top", [])
            ],
            [16, 40, 40, 26, 21, 19, 18, 70],
            empty="Нет каналов с уровнем «внимание» или «критично».",
        )

    report.heading("Что произошло")
    if not happened.get("available"):
        report.note("Журнал событий за смену недоступен.")
    else:
        kinds = happened.get("kinds", {})
        report.table(
            ["Вид события", "Количество"],
            [[KINDS.get(key, key), value] for key, value in sorted(kinds.items())],
            [80, 30],
        )
        if happened.get("truncated"):
            report.note("Событий больше, чем показано в сводке: учтены последние 500.")
        objects = happened.get("objects", [])
        if objects:
            report.heading("Объекты с наибольшим числом событий")
            report.table(
                ["Объект", "Событий"],
                [[item["object_id"], item["events"]] for item in objects],
                [80, 30],
            )
        report.heading("Последние события")
        report.table(
            ["Время", "Объект", "Канал", "Название", "Состояние", "Тревога"],
            [
                [
                    _local(item.get("ts"), zone),
                    item.get("object_id"),
                    item.get("channel_id"),
                    item.get("name"),
                    item.get("value"),
                    "да" if item.get("alarm") else "нет",
                ]
                for item in happened.get("latest", [])
            ],
            [28, 18, 18, 60, 40, 14],
        )

    report.heading("Что сделано")
    report.table(
        ["Канал", "Работа", "Исход", "Примечание", "Завершена"],
        [
            [
                item.get("asset_id"),
                item.get("reason"),
                OUTCOMES.get(item.get("outcome") or "", item.get("outcome")),
                item.get("note"),
                _local(item.get("completed_at"), zone),
            ]
            for item in done.get("completed_items", [])
        ],
        [18, 90, 30, 60, 26],
        empty="За смену работы не завершались.",
    )
    return report.render()
