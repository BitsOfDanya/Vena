import csv
import json
import re
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal

router = APIRouter(prefix="/ml", tags=["ml"])

RESULT_GROUPS = ("tables", "formal_70_50", "new_directions")
REPORTS = (
    "seasonality",
    "calibration",
    "incident_calibration",
    "access_analysis",
    "flood_variants",
    "sustained_study",
    "model_report",
    "refit_study",
    "detection_study",
    "health_index",
    "workload_forecast",
)
FILE_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.csv$")
MAX_ROWS = 1000

SettingsDep = Annotated[Settings, Depends(get_settings)]
ReaderDep = Annotated[Principal, Depends(get_principal)]


def _read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _result_file(settings: Settings, group: str, name: str) -> Path:
    if group not in RESULT_GROUPS or not FILE_NAME.match(name):
        raise HTTPException(status_code=404, detail="result not found")
    base = (settings.ml_dir / "results" / group).resolve()
    path = (base / name).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="result not found")
    return path


@router.get("/directions")
def list_directions(settings: SettingsDep, _: ReaderDep) -> list[dict[str, Any]]:
    path = settings.ml_dir / "results" / "directions.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="directions not available")
    directions: list[dict[str, Any]] = _read_json(path)
    return directions


@router.get("/prospective")
def get_prospective(settings: SettingsDep, _: ReaderDep) -> Any:
    path = settings.ml_dir / "results" / "predictions" / "prospective.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="prospective check has not started")
    return _read_json(path)


@router.get("/reports/{name}")
def get_report(name: str, settings: SettingsDep, _: ReaderDep) -> Any:
    path = settings.ml_dir / "results" / f"{name}.json"
    if name not in REPORTS or not path.is_file():
        raise HTTPException(status_code=404, detail="report not found")
    return _read_json(path)


@router.get("/models")
def list_models(settings: SettingsDep, _: ReaderDep) -> list[dict[str, Any]]:
    registry = settings.ml_dir / "results" / "models.json"
    if registry.is_file():
        cards: list[dict[str, Any]] = _read_json(registry)
        return cards
    models: list[dict[str, Any]] = []
    for path in sorted((settings.ml_dir / "configs" / "models").glob("*.json")):
        config = _read_json(path)
        model = config.get("model", {})
        models.append(
            {
                "name": path.stem,
                "horizon_hours": model.get("horizon_hours"),
                "recipe": model.get("model_name"),
                "features": len(config.get("feature_columns", [])),
                "train_years": (config.get("training_period") or {}).get("train_years"),
            }
        )
    return models


@router.get("/results")
def list_results(settings: SettingsDep, _: ReaderDep) -> dict[str, list[str]]:
    root = settings.ml_dir / "results"
    return {group: sorted(p.name for p in (root / group).glob("*.csv")) for group in RESULT_GROUPS}


@router.get("/results/{group}/{name}")
def get_result(
    group: str,
    name: str,
    settings: SettingsDep,
    _: ReaderDep,
    limit: Annotated[int, Query(ge=1, le=MAX_ROWS)] = 200,
) -> dict[str, Any]:
    path = _result_file(settings, group, name)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = [row for _, row in zip(range(limit), reader, strict=False)]
        columns = list(reader.fieldnames or [])
    return {"group": group, "name": name, "columns": columns, "rows": rows}
