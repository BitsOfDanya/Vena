"""Typical actions per incident scenario from ml/configs/recommendations.json."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.schemas.predictions import Prediction
from app.schemas.system import Recommendation


@lru_cache(maxsize=4)
def _catalogue(path: Path, mtime: float) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data: dict[str, Any] = json.load(handle)
    return data


def recommend(settings: Settings, scenario: str, lead: Prediction) -> Recommendation | None:
    path = settings.ml_dir / "configs" / "recommendations.json"
    if not path.is_file():
        return None
    catalogue = _catalogue(path, path.stat().st_mtime)
    entry = catalogue.get("scenarios", {}).get(scenario)
    if entry is None:
        return None
    hints = catalogue.get("drivers", {})
    hint = next((hints[driver.feature] for driver in lead.drivers if driver.feature in hints), None)
    return Recommendation(
        title=entry["title"],
        actions=list(entry["actions"]),
        hint=hint,
        note=catalogue.get("note", ""),
    )
