import csv
import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ImportBatch,
    InfrastructureObject,
    NetworkEdge,
    SensorChannel,
    TelemetryEvent,
)

ALIASES = {
    "source_record_id": ("source_record_id", "event_id", "ид записи журнала", "ид записи"),
    "channel_id": ("channel_id", "ид канала данных"),
    "channel_type": ("channel_type", "ид типа канала данных", "тип датчика"),
    "value": ("value", "текущее значение", "значение"),
    "occurred_at": ("occurred_at", "дата записи", "дата события"),
    "object_tag": ("object_tag", "тег в дереве объектов", "тег"),
    "display_name": ("display_name", "диспетчерское название"),
    "object_id": ("object_id", "ид объекта", "ид системы"),
    "name": ("name", "название", "диспетчерское название"),
    "system_name": ("system_name", "система"),
    "latitude": ("latitude", "lat", "широта"),
    "longitude": ("longitude", "lon", "lng", "долгота"),
    "district": ("district", "округ", "район"),
    "object_type": ("object_type", "тип объекта"),
    "status": ("status", "состояние"),
    "edge_id": ("edge_id", "ид связи"),
    "source_id": ("source_id", "исходный объект"),
    "target_id": ("target_id", "целевой объект"),
    "kind": ("kind", "тип связи"),
}
REQUIRED = {
    "events": ("source_record_id", "channel_id", "value", "occurred_at"),
    "channels": ("channel_id", "object_tag"),
    "objects": ("object_id", "name"),
    "edges": ("source_id", "target_id"),
}


def _normalized(row: dict[str, Any]) -> dict[str, str]:
    return {
        str(key).strip().casefold(): str(value).strip() if value is not None else ""
        for key, value in row.items()
        if key is not None
    }


def _field(row: dict[str, str], name: str) -> str:
    return next((row[alias] for alias in ALIASES[name] if row.get(alias)), "")


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook.active
            if sheet is None:
                return
            iterator = sheet.iter_rows(values_only=True)
            headers = [
                str(value).strip() if value is not None else "" for value in next(iterator, ())
            ]
            for values in iterator:
                yield dict(zip(headers, values, strict=False))
        finally:
            workbook.close()
    else:
        with path.open("rb") as binary:
            header = binary.read(8192)
        try:
            sample = header.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            sample = header.decode("cp1251")
            encoding = "cp1251"
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
            delimiter = dialect.delimiter
        except csv.Error:
            delimiter = ";" if sample.count(";") > sample.count(",") else ","
        with path.open(encoding=encoding, newline="") as stream:
            yield from csv.DictReader(stream, delimiter=delimiter)


def _date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = datetime.strptime(value, "%d.%m.%Y %H:%M")
    if parsed.tzinfo:
        return parsed
    return parsed.replace(tzinfo=ZoneInfo("Europe/Moscow")).astimezone(UTC)


def _apply(session: Session, batch: ImportBatch, row: dict[str, str]) -> bool:
    missing = [name for name in REQUIRED[batch.kind] if not _field(row, name)]
    if missing:
        raise ValueError(f"Missing fields: {', '.join(missing)}")
    if batch.kind == "channels":
        channel_id = _field(row, "channel_id")
        item = session.get(SensorChannel, channel_id)
        if item is None:
            item = SensorChannel(id=channel_id)
            session.add(item)
        item.object_tag = _field(row, "object_tag")
        item.channel_type = _field(row, "channel_type")
        item.display_name = _field(row, "display_name")
        return True
    if batch.kind == "objects":
        object_id = _field(row, "object_id")
        latitude = _field(row, "latitude")
        longitude = _field(row, "longitude")
        if bool(latitude) != bool(longitude):
            raise ValueError("Latitude and longitude must be provided together")
        coordinates: tuple[float, float] | None = None
        if latitude:
            lat = float(latitude.replace(",", "."))
            lon = float(longitude.replace(",", "."))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("Coordinates are out of range")
            coordinates = (lat, lon)
        infra_object = session.get(InfrastructureObject, object_id)
        if infra_object is None:
            infra_object = InfrastructureObject(id=object_id)
            session.add(infra_object)
        infra_object.name = _field(row, "name")
        infra_object.system_name = _field(row, "system_name")
        infra_object.tag = _field(row, "object_tag")
        infra_object.district = _field(row, "district")
        infra_object.object_type = _field(row, "object_type") or "collector"
        infra_object.status = _field(row, "status") or "normal"
        if coordinates:
            infra_object.latitude, infra_object.longitude = coordinates
        infra_object.is_demo = False
        return True
    if batch.kind == "edges":
        source_id = _field(row, "source_id")
        target_id = _field(row, "target_id")
        if source_id == target_id:
            raise ValueError("Network link must connect two objects")
        if session.get(InfrastructureObject, source_id) is None:
            raise ValueError(f"Unknown source object: {source_id}")
        if session.get(InfrastructureObject, target_id) is None:
            raise ValueError(f"Unknown target object: {target_id}")
        kind = _field(row, "kind") or "collector"
        edge_id = _field(row, "edge_id") or hashlib.sha256(
            f"{source_id}:{target_id}:{kind}".encode()
        ).hexdigest()[:32]
        edge = session.get(NetworkEdge, edge_id)
        if edge is None:
            edge = NetworkEdge(id=edge_id)
            session.add(edge)
        edge.source_id = source_id
        edge.target_id = target_id
        edge.kind = kind
        edge.is_demo = False
        return True
    source_id = _field(row, "source_record_id")
    channel_id = _field(row, "channel_id")
    existing = session.scalar(
        select(TelemetryEvent.id).where(
            TelemetryEvent.source_record_id == source_id,
            TelemetryEvent.channel_id == channel_id,
        )
    )
    if existing is not None:
        return False
    raw = _field(row, "value")
    try:
        numeric = float(raw.replace(",", "."))
    except ValueError:
        numeric = None
    session.add(
        TelemetryEvent(
            source_record_id=source_id,
            channel_id=channel_id,
            channel_type=_field(row, "channel_type"),
            value_raw=raw,
            value_numeric=numeric,
            occurred_at=_date(_field(row, "occurred_at")),
            import_batch_id=batch.id,
        )
    )
    return True


def process_batch(session: Session, batch: ImportBatch) -> None:
    batch.status = "processing"
    session.commit()
    errors: list[str] = []
    try:
        for number, raw in enumerate(_rows(Path(batch.file_path)), start=2):
            row = _normalized(raw)
            if not any(row.values()):
                continue
            batch.total_rows += 1
            try:
                if _apply(session, batch, row):
                    batch.accepted_rows += 1
            except (ValueError, TypeError) as error:
                batch.rejected_rows += 1
                if len(errors) < 10:
                    errors.append(f"Строка {number}: {error}")
            if batch.total_rows % 500 == 0:
                session.commit()
        batch.status = "completed" if batch.rejected_rows == 0 else "completed_with_errors"
        batch.error = "\n".join(errors)
    except Exception as error:
        session.rollback()
        batch = session.get(ImportBatch, batch.id) or batch
        batch.status = "failed"
        batch.error = str(error)[:2000]
    batch.finished_at = datetime.now(tz=UTC)
    session.commit()
