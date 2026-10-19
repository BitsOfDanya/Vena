import re

import sqlalchemy as sa
from alembic import op

revision = "b5d1e7c3a9f2"
down_revision = "b5d2e8f41c07"
branch_labels = None
depends_on = None

LEVELS = {
    "critical": "критично",
    "attention": "внимание",
    "observe": "наблюдение",
    "normal": "норма",
}
MODELS = {
    "phase": "Питание",
    "power": "Питание",
    "pump": "Подтопление",
    "flood": "Подтопление",
    "smoke": "Пожар",
    "fan": "Вентиляция",
    "alarm": "Тревоги",
}
REASON = re.compile(
    r"^(?P<title>.+?): ML (?P<model>\S+) (?P<level>\w+) risk (?P<score>\S+) over (?P<hours>\d+)h"
    r"(?:; (?P<count>\d+) channels at this location)?$"
)
DESCRIPTION = re.compile(
    r"^Model (?P<model>\S+) reports (?P<level>\w+) risk for the next (?P<hours>\d+)h"
    r"(?:, (?P<delta>[+-]?[\d.]+) since the previous snapshot)?\."
    r"(?: (?P<count>\d+) channels at this location share the risk\.)?"
    r" Main reason: (?P<reason>.*)$",
    re.DOTALL,
)
DRAFT = re.compile(
    r"^(?P<title>.+?): модель (?P<model>\S+), уровень (?P<level>[^,]+), вероятность "
    r"(?P<score>.+?) за (?P<hours>\d+) ч(?:; каналов на локации: (?P<count>\d+))?$"
)
MODEL_PREFIX = re.compile(r"^Модель (?P<model>[a-z0-9_]+): уровень ")
TITLE = re.compile(r"^(?P<head>.+) · (?P<model>[a-z_]+_(?P<hours>\d+)h) (?P<score>\S+)$")


def _model(model_id: str) -> str:
    base = MODELS.get(model_id.split("_", 1)[0])
    if base is None:
        return model_id
    hours = "3 суток" if "72" in model_id else "сутки" if "24" in model_id else None
    return f"{base}, {hours}" if hours else base


def _reason(text: str) -> str | None:
    match = REASON.match(text) or DRAFT.match(text)
    if not match:
        return None
    scenario, _, place = match["title"].partition(" · ")
    level = LEVELS.get(match["level"], match["level"])
    scope = f" Каналов на локации: {match['count']}." if match["count"] else ""
    return (
        f"Прогноз: {scenario.lower()}, {level}, {match['score']} за {match['hours']} ч. "
        f"Место: {place or scenario}.{scope}"
    )


def _description(text: str) -> str | None:
    current = MODEL_PREFIX.match(text)
    if current:
        return f"Прогноз «{_model(current['model'])}»: уровень {text[current.end() :]}"
    match = DESCRIPTION.match(text)
    if not match:
        return None
    change = f", изменение {match['delta']} с прошлого снимка" if match["delta"] else ""
    scope = f" Риск разделяют каналов на локации: {match['count']}." if match["count"] else ""
    return (
        f"Прогноз «{_model(match['model'])}»: уровень "
        f"{LEVELS.get(match['level'], match['level'])} на {match['hours']} ч{change}.{scope} "
        f"Главная причина: {match['reason']}"
    )


def _title(text: str) -> str | None:
    match = TITLE.match(text)
    if not match:
        return None
    return f"{match['head']} · {match['score']} за {match['hours']} ч"


def upgrade():
    bind = op.get_bind()
    actions = bind.execute(
        sa.text("SELECT id, reason, note FROM actions WHERE source = 'vena_forecast'")
    ).fetchall()
    for action_id, reason, note in actions:
        new_reason = _reason(reason or "") or reason
        new_note = (
            "Черновик создан по прогнозу модели"
            if note == "Auto-draft from prediction ingest"
            else note
        )
        if new_reason != reason or new_note != note:
            bind.execute(
                sa.text("UPDATE actions SET reason = :reason, note = :note WHERE id = :id"),
                {"reason": new_reason, "note": new_note, "id": action_id},
            )
    notifications = bind.execute(
        sa.text("SELECT id, title, description FROM notifications WHERE type = 'risk'")
    ).fetchall()
    for notification_id, title, description in notifications:
        new_title = _title(title or "") or title
        new_description = _description(description or "") or description
        if new_title != title or new_description != description:
            bind.execute(
                sa.text(
                    "UPDATE notifications SET title = :title, description = :description "
                    "WHERE id = :id"
                ),
                {"title": new_title, "description": new_description, "id": notification_id},
            )


def downgrade():
    pass
