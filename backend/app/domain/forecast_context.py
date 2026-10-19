import json
from datetime import date, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.schemas.predictions import ContextLine, Prediction

MONTHS = (
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
)
MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
WEEKDAYS_SHORT = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
HOLIDAYS = {
    **{(1, day): "новогодние каникулы" for day in range(1, 9) if day != 7},
    (1, 7): "Рождество Христово",
    (2, 23): "День защитника Отечества",
    (3, 8): "Международный женский день",
    (5, 1): "Праздник Весны и Труда",
    (5, 9): "День Победы",
    (6, 12): "День России",
    (11, 4): "День народного единства",
}
SEASONALITY_SCENARIO = {
    "pump": "pump_fault",
    "fan": "ventilation_fault",
    "smoke": "smoke_sensor_fault",
    "smoke_alarm": "smoke_detected",
    "phase": "power_loss",
    "power": "power_loss",
    "flood": "flooding",
}
SEASONALITY_EVENTS = {
    "pump_fault": "отказов насосов",
    "ventilation_fault": "отказов вентиляторов",
    "smoke_sensor_fault": "неисправностей датчиков дыма",
    "smoke_detected": "срабатываний датчиков дыма",
    "power_loss": "отключений питания",
    "flooding": "затоплений камер",
}
SEASONALITY_NEUTRAL = 0.05


@lru_cache(maxsize=2)
def _seasonality(path: str, mtime: float) -> dict[str, dict[int, float]]:
    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle).get("monthly_onsets_per_100_channels") or {}
    return {
        str(scenario): {int(month): float(value) for month, value in months.items()}
        for scenario, months in raw.items()
        if isinstance(months, dict)
    }


def load_seasonality(settings: Settings) -> dict[str, dict[int, float]]:
    path = settings.ml_dir / "results" / "seasonality.json"
    if not path.is_file():
        return {}
    try:
        return _seasonality(str(path), path.stat().st_mtime)
    except (OSError, ValueError, TypeError, AttributeError):
        return {}


def forecast_days(prediction: Prediction, timezone: str) -> list[date]:
    hours = prediction.horizon_hours or 24
    count = max(1, round(hours / 24))
    start = prediction.prediction_time.astimezone(ZoneInfo(timezone))
    first = start + timedelta(hours=hours / 2) - timedelta(days=(count - 1) / 2)
    return [first.date() + timedelta(days=index) for index in range(count)]


def _day(day: date) -> str:
    return f"{day.day} {MONTHS_GENITIVE[day.month - 1]}"


def _span(days: list[date]) -> str:
    first, last = days[0], days[-1]
    if first.month == last.month:
        return f"{first.day}–{last.day} {MONTHS_GENITIVE[last.month - 1]}"
    return f"{_day(first)} – {_day(last)}"


def calendar_line(days: list[date]) -> ContextLine:
    reasons = {
        day: HOLIDAYS.get((day.month, day.day)) or ("выходной" if day.weekday() >= 5 else None)
        for day in days
    }
    if len(days) == 1:
        day = days[0]
        reason = reasons[day]
        if reason is None:
            status = "рабочий день"
        elif reason == "выходной":
            status = "выходной день"
        else:
            status = f"нерабочий праздничный день ({reason})"
        weekday = WEEKDAYS[day.weekday()].capitalize()
        return ContextLine(label="Календарь", text=f"{weekday}, {_day(day)} — {status}")
    first, last = WEEKDAYS_SHORT[days[0].weekday()], WEEKDAYS_SHORT[days[-1].weekday()]
    head = f"{_span(days)}, {first}–{last}"
    off = [
        f"{WEEKDAYS_SHORT[day.weekday()]} {_day(day)}"
        + (f" ({reason})" if reason != "выходной" else "")
        for day, reason in reasons.items()
        if reason
    ]
    if not off:
        return ContextLine(label="Календарь", text=f"{head} — рабочие дни")
    return ContextLine(label="Календарь", text=f"{head} — нерабочие: {', '.join(off)}")


def seasonality_line(
    prediction: Prediction, month: int, seasonality: dict[str, dict[int, float]]
) -> ContextLine | None:
    device = prediction.device_type or prediction.model_id.rsplit("_", 1)[0]
    scenario = SEASONALITY_SCENARIO.get(device)
    months = seasonality.get(scenario or "")
    if not scenario or not months or month not in months:
        return None
    mean = sum(months.values()) / len(months)
    if mean <= 0:
        return None
    ratio = months[month] / mean - 1
    events = SEASONALITY_EVENTS[scenario]
    if abs(ratio) < SEASONALITY_NEUTRAL:
        text = f"{MONTHS[month - 1]}: {events} обычно столько же, сколько в среднем за месяц"
    else:
        direction = "больше" if ratio > 0 else "меньше"
        text = (
            f"{MONTHS[month - 1]}: {events} обычно на {abs(ratio):.0%} {direction}, "
            "чем в среднем за месяц"
        )
    return ContextLine(label="Сезонность", text=text)


def weather_line(days: list[date], weather: list[dict[str, Any]]) -> ContextLine | None:
    wanted = {day.isoformat() for day in days}
    rows = [row for row in weather if str(row.get("day")) in wanted]
    lows = [row["temp_min"] for row in rows if isinstance(row.get("temp_min"), int | float)]
    highs = [row["temp_max"] for row in rows if isinstance(row.get("temp_max"), int | float)]
    if not lows or not highs:
        return None
    rain = sum(
        float(row["precipitation_mm"])
        for row in rows
        if isinstance(row.get("precipitation_mm"), int | float)
    )
    parts = [
        f"{min(lows):+.0f}…{max(highs):+.0f} °C",
        f"осадки {rain:.1f} мм".replace(".", ",") if rain else "без осадков",
    ]
    if any(row.get("thaw") for row in rows):
        parts.append("переход через 0 °C")
    return ContextLine(label="Погода", text=", ".join(parts))


def build_context(
    prediction: Prediction,
    seasonality: dict[str, dict[int, float]],
    weather: list[dict[str, Any]],
    timezone: str,
) -> list[ContextLine]:
    days = forecast_days(prediction, timezone)
    lines = [
        seasonality_line(prediction, days[len(days) // 2].month, seasonality),
        calendar_line(days),
        weather_line(days, weather),
    ]
    return [line for line in lines if line]
