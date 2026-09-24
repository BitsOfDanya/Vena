import hashlib
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import require_operator
from app.core.config import Settings, get_settings
from app.db.models import ImportBatch, User
from app.db.session import get_session

router = APIRouter(prefix="/imports", tags=["imports"])
SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
OperatorDep = Annotated[User, Depends(require_operator)]
ImportKind = Literal["events", "channels", "objects", "edges"]


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: ImportKind
    filename: str
    size_bytes: int
    status: str
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    error: str
    created_at: datetime
    finished_at: datetime | None


@router.get("", response_model=list[ImportOut])
def list_imports(session: SessionDep) -> list[ImportBatch]:
    return list(
        session.scalars(select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(100))
    )


@router.get("/{batch_id}", response_model=ImportOut)
def get_import(batch_id: str, session: SessionDep) -> ImportBatch:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return batch


@router.post("", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
def upload_import(
    file: UploadFile,
    kind: ImportKind,
    session: SessionDep,
    settings: SettingsDep,
    user: OperatorDep,
) -> ImportBatch:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Only CSV and XLSX files are supported")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    batch_id = uuid4().hex
    path = settings.upload_dir / f"{batch_id}{suffix}"
    digest = hashlib.sha256()
    size = 0
    signature = b""
    try:
        with path.open("wb") as output:
            while chunk := file.file.read(1024 * 1024):
                if not signature:
                    signature = chunk[:8]
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="File is too large")
                digest.update(chunk)
                output.write(chunk)
        if size == 0:
            raise HTTPException(status_code=422, detail="File is empty")
        if suffix == ".xlsx" and not signature.startswith(b"PK"):
            raise HTTPException(status_code=415, detail="Invalid XLSX file")
        if suffix == ".csv" and b"\x00" in signature:
            raise HTTPException(status_code=415, detail="Invalid CSV file")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    duplicate = session.scalar(
        select(ImportBatch.id).where(
            ImportBatch.kind == kind,
            ImportBatch.sha256 == digest.hexdigest(),
            ImportBatch.status != "failed",
        )
    )
    if duplicate:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=f"File already imported: {duplicate}")
    batch = ImportBatch(
        id=batch_id,
        kind=kind,
        filename=Path(file.filename or "upload").name[:255],
        file_path=str(path.resolve()),
        sha256=digest.hexdigest(),
        size_bytes=size,
        created_by=user.id,
    )
    session.add(batch)
    session.flush()
    return batch
