import json
import re
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


def load_catalogue(settings: Settings) -> dict[str, Any]:
    path = settings.ml_dir / "configs" / "recommendations.json"
    if not path.is_file():
        return {}
    return _catalogue(path, path.stat().st_mtime)


def driver_hints(settings: Settings) -> dict[str, str]:
    catalogue = load_catalogue(settings)
    raw = catalogue.get("drivers", {})
    return {str(key): str(value) for key, value in raw.items()}


def recommend(settings: Settings, scenario: str, lead: Prediction) -> Recommendation | None:
    catalogue = load_catalogue(settings)
    entry = catalogue.get("scenarios", {}).get(scenario)
    if entry is None:
        return None
    hints = catalogue.get("drivers", {})
    hint = next((hints[driver.feature] for driver in lead.drivers if driver.feature in hints), None)
    actions = list(entry["actions"])
    feeder = _feeder(catalogue, lead, scenario)
    if feeder:
        actions.insert(0, feeder["action"])
    what = None
    if feeder:
        what = feeder.get("what") or _what_from_feeder(feeder, scenario)
    if not what:
        what = entry.get("what")
    consequence = None
    if feeder:
        consequence = feeder.get("consequence")
    if not consequence:
        consequence = entry.get("consequence")
    return Recommendation(
        title=entry["title"],
        actions=actions,
        hint=hint,
        note=catalogue.get("note", ""),
        what=str(what) if what else None,
        feeder=feeder["kind"] if feeder else None,
        consequence=str(consequence) if consequence else None,
    )


def _what_from_feeder(feeder: dict[str, str], scenario: str) -> str:
    kind = feeder.get("kind") or "канал"
    if scenario == "power_loss":
        return f"Обесточится {kind[0].lower() + kind[1:]}" if kind else "Обесточится фидер"
    return kind


def _feeder(catalogue: dict[str, Any], lead: Prediction, scenario: str) -> dict[str, str] | None:
    """Match by channel name, location tag, or asset id; prefer feeders for this scenario."""
    haystack = " ".join(
        part
        for part in (lead.name, lead.location_tag, lead.location, lead.asset_id)
        if part
    )
    exact: dict[str, str] | None = None
    fallback: dict[str, str] | None = None
    for feeder in catalogue.get("feeders", []):
        if not re.search(str(feeder["pattern"]), haystack, flags=re.IGNORECASE):
            continue
        item = {key: str(value) for key, value in feeder.items()}
        feeder_scenario = item.get("scenario") or ""
        if feeder_scenario == scenario:
            exact = item
            break
        if fallback is None:
            fallback = item
    return exact or fallback
