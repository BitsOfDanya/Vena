import json
from datetime import timedelta
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import Principal, get_principal, require_min_role
from app.db.models import Equipment, HistoricalEvent, ImportOutbox, IntegrationRun
from app.db.session import get_session
from app.domain import equipment, imports, journal_tail
from app.schemas.equipment import EquipmentIn, EquipmentOut

router = APIRouter(tags=["equipment", "imports"])
DB = Annotated[Session, Depends(get_session)]
Config = Annotated[Settings, Depends(get_settings)]
Reader = Annotated[Principal, Depends(get_principal)]
Admin = Annotated[Principal, Depends(require_min_role("admin"))]


def run_dict(run: IntegrationRun) -> dict:
    return {
        "id": run.id,
        "kind": run.kind,
        "source": run.source,
        "status": run.status,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "detail": run.detail,
        **json.loads(run.result),
    }


@router.get("/equipment")
def list_equipment(
    db: DB,
    _: Reader,
    q: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
) -> dict:
    query = select(Equipment)
    if q:
        query = query.where(
            Equipment.name.ilike(f"%{q}%")
            | Equipment.asset_id.ilike(f"%{q}%")
            | Equipment.object_id.ilike(f"%{q}%")
        )
    count = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Equipment.object_id, Equipment.asset_id).offset(offset).limit(limit)
    )
    return {"total": count, "items": [EquipmentOut.model_validate(row) for row in rows]}


@router.get("/integrations/status")
def integration_status(db: DB, settings: Config, _: Reader) -> dict:
    from app.domain.predictions import get_prediction_source

    snapshot = get_prediction_source(settings).status()
    worker_path = settings.ml_dir / "results" / "predictions" / "worker-status.json"
    try:
        worker = json.loads(worker_path.read_text())
    except (OSError, ValueError):
        worker = {}
    return {
        "data_source": snapshot.data_source,
        "prediction_count": snapshot.prediction_count,
        "worker": worker,
        "equipment_count": db.scalar(select(func.count()).select_from(Equipment)),
        "journal_events": db.scalar(select(func.count()).select_from(HistoricalEvent)),
        "pending_publications": db.scalar(
            select(func.count())
            .select_from(ImportOutbox)
            .where(ImportOutbox.delivered_at.is_(None))
        ),
        "upload_configured": settings.dataset_dir is not None,
        "sync_configured": bool(settings.equipment_sync_enabled and settings.equipment_sync_url),
        "sync_interval_seconds": settings.equipment_sync_interval_seconds,
        "ldap_enabled": settings.ldap_enabled,
        "ldap_configured": settings.ldap_configured,
        "runs": [
            run_dict(run)
            for run in db.scalars(
                select(IntegrationRun).order_by(IntegrationRun.started_at.desc()).limit(20)
            )
        ],
    }


@router.post("/equipment/sync")
def sync_equipment(db: DB, settings: Config, principal: Admin) -> dict:
    try:
        return run_dict(equipment.synchronize(db, settings, principal.subject))
    except equipment.RegistryError as error:
        raise HTTPException(409, str(error)) from None


class RegistryBody(BaseModel):
    items: list[EquipmentIn] = Field(max_length=100_000)


@router.put("/equipment")
def update_equipment(body: RegistryBody, db: DB, settings: Config, principal: Admin) -> dict:
    from app.domain import audit

    try:
        equipment.lock_registry(db)
        result = equipment.upsert(db, body.items, settings.equipment_sync_source)
        equipment.queue_registry(db)
        audit.record(
            db,
            actor=principal.subject,
            role=principal.role,
            action="equipment.update",
            resource_type="equipment",
            detail=json.dumps(result),
        )
        return result
    except equipment.RegistryError as error:
        raise HTTPException(409, str(error)) from None


@router.post("/imports")
def upload(
    file: UploadFile,
    db: DB,
    settings: Config,
    principal: Admin,
    kind: Literal["channels", "journal"] = "channels",
) -> dict:
    try:
        return run_dict(
            imports.preview(db, settings, file.file, file.filename or "", kind, principal.subject)
        )
    except equipment.RegistryError as error:
        raise HTTPException(400, str(error)) from None
    finally:
        file.file.close()


@router.post("/imports/{run_id}/apply")
def apply_upload(run_id: str, db: DB, settings: Config, principal: Admin) -> dict:
    run = db.get(IntegrationRun, run_id)
    if run is None or run.kind not in {"journal", "channels"}:
        raise HTTPException(404, "Загрузка не найдена")
    try:
        return run_dict(imports.apply_import(db, settings, run, principal.subject))
    except equipment.RegistryError as error:
        raise HTTPException(409, str(error)) from None
    except OSError:
        raise HTTPException(503, "Хранилище загрузок недоступно") from None


@router.get("/imports/template/{kind}.xlsx")
def template(kind: Literal["channels", "journal"], _: Admin) -> Response:
    book = Workbook()
    sheet = book.worksheets[0]
    sheet.title = "Данные"
    sheet.append(
        [
            "ид_канала_данных",
            "название_датчика",
            "тип_датчика",
            "тег_инженерной_системы",
            "тип_инж_системы",
            "ид_объект",
        ]
        if kind == "channels"
        else imports.EVENT_HEADERS
    )
    sheet.freeze_panes = "A2"
    output = BytesIO()
    book.save(output)
    return Response(
        output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{kind}.xlsx"'},
    )


@router.get("/events/recent")
def recent_events(
    db: DB,
    settings: Config,
    _: Reader,
    hours: int = Query(6, ge=1, le=168),
    limit: int = Query(100, ge=1, le=500),
    channel_id: str | None = None,
) -> dict:
    query = select(HistoricalEvent, Equipment.name, Equipment.object_id).outerjoin(
        Equipment, Equipment.asset_id == HistoricalEvent.channel_id
    )
    latest_query = select(func.max(HistoricalEvent.ts))
    if channel_id:
        latest_query = latest_query.where(HistoricalEvent.channel_id == channel_id)
        query = query.where(HistoricalEvent.channel_id == channel_id)
    latest = db.scalar(latest_query)
    if latest is None:
        if settings.dataset_dir is not None and settings.dataset_dir.is_dir():
            return journal_tail.recent(
                settings.dataset_dir, hours, limit, channel_id, settings.timezone
            )
        return {"latest_at": None, "from": None, "items": [], "has_more": False}
    start = latest - timedelta(hours=hours)
    rows = list(
        db.execute(
            query.where(HistoricalEvent.ts >= start)
            .order_by(HistoricalEvent.ts.desc(), HistoricalEvent.event_id.desc())
            .limit(limit + 1)
        )
    )
    return {
        "latest_at": latest,
        "from": start,
        "has_more": len(rows) > limit,
        "items": [
            {
                "event_id": event.event_id,
                "channel_id": event.channel_id,
                "ts": event.ts,
                "value": event.value,
                "alarm": event.alarm,
                "name": name or event.channel_id,
                "object_id": object_id,
            }
            for event, name, object_id in rows[:limit]
        ],
    }
