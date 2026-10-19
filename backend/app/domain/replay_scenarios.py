import json
from dataclasses import replace
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.core.config import Settings
from app.domain.replay_reader import JournalRow
from app.schemas.replay import ScenarioCatalog, ScenarioItem

STAGES = ("предвестники", "развитие", "инцидент")
PRECURSOR_HOURS = 6


def load_catalog(settings: Settings) -> ScenarioCatalog:
    path = settings.ml_dir / "results" / "scenarios" / "catalog.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ScenarioCatalog()
    if not isinstance(raw, dict):
        return ScenarioCatalog()
    items = []
    for item in raw.get("items") or []:
        try:
            items.append(ScenarioItem.model_validate(item))
        except ValidationError:
            continue
    try:
        return ScenarioCatalog.model_validate({**raw, "items": items})
    except ValidationError:
        return ScenarioCatalog(items=items)


def find(settings: Settings, scenario_id: str) -> ScenarioItem | None:
    return next((item for item in load_catalog(settings).items if item.id == scenario_id), None)


def window(item: ScenarioItem) -> tuple[datetime, datetime]:
    return (
        item.start - timedelta(hours=item.before_hours),
        max(item.end, item.start) + timedelta(hours=item.after_hours),
    )


def shift_days(first: datetime, clock: datetime | None) -> int:
    if clock is None:
        return 0
    return max(0, (clock - first).days + 1)


def split_stages(
    rows: list[JournalRow], incident_start: datetime, days: int
) -> list[tuple[str, list[JournalRow]]]:
    delta = timedelta(days=days)
    bounds = (incident_start - timedelta(hours=PRECURSOR_HOURS), incident_start)
    parts: dict[str, list[JournalRow]] = {name: [] for name in STAGES}
    for row in rows:
        index = sum(row.ts >= bound for bound in bounds)
        parts[STAGES[index]].append(replace(row, ts=row.ts + delta))
    return [(name, items) for name, items in parts.items() if items]
