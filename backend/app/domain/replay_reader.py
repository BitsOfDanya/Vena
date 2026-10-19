import csv
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO

from app.domain.journal_tail import journal_files

PROBE_LINES = 64
BLOCK = 1 << 16
TAIL = 1 << 12
PAD = timedelta(hours=3)


@dataclass(frozen=True)
class JournalRow:
    event_id: str
    channel_id: str
    ts: datetime
    alarm: bool
    value: str


def _fields(line: str) -> list[str]:
    line = line.strip()
    if '"' in line:
        return next(csv.reader([line]), [])
    return line.split(",", 5)


def _timestamp(fields: list[str]) -> datetime | None:
    try:
        return datetime.fromisoformat(f"{fields[2].strip()}T{fields[3].strip()}")
    except (IndexError, ValueError):
        return None


def parse_line(line: str) -> JournalRow | None:
    return _row(_fields(line))


def _row(fields: list[str]) -> JournalRow | None:
    if len(fields) < 6:
        return None
    ts = _timestamp(fields)
    if ts is None:
        return None
    return JournalRow(
        event_id=fields[0].strip(),
        channel_id=fields[1].strip(),
        ts=ts,
        alarm=fields[4].strip().lower() in {"t", "true", "1"},
        value=fields[5].strip(),
    )


def _probe(
    handle: BinaryIO, offset: int, lines: int = PROBE_LINES, quantile: float = 0.5
) -> datetime | None:
    handle.seek(offset)
    if offset:
        handle.readline()
    stamps = []
    for _ in range(lines):
        raw = handle.readline()
        if not raw:
            break
        ts = _timestamp(_fields(raw.decode("utf-8", errors="ignore")))
        if ts is not None:
            stamps.append(ts)
    if not stamps:
        return None
    stamps.sort()
    return stamps[int((len(stamps) - 1) * quantile)]


def locate(path: Path, target: datetime) -> tuple[int, int]:
    size = path.stat().st_size
    low, high = 0, size
    with path.open("rb") as handle:
        while high - low > BLOCK:
            middle = (low + high) // 2
            stamp = _probe(handle, middle)
            if stamp is not None and stamp < target:
                low = middle
            else:
                high = middle
    return low, high


@lru_cache(maxsize=64)
def _span(path: str, size: int, mtime: float) -> tuple[datetime, datetime] | None:
    with open(path, "rb") as handle:
        first = _probe(handle, 0, quantile=0.1)
        last = _probe(handle, max(size - TAIL, 0), TAIL, 0.9)
    if first is None or last is None:
        return None
    return first, last


def file_span(path: Path) -> tuple[datetime, datetime] | None:
    stat = path.stat()
    return _span(str(path), stat.st_size, stat.st_mtime)


def journal_range(dataset: Path) -> tuple[datetime, datetime] | None:
    spans = [span for path in journal_files(dataset) if (span := file_span(path))]
    if not spans:
        return None
    return min(span[0] for span in spans), max(span[1] for span in spans)


def read_window(
    dataset: Path, start: datetime, end: datetime, channels: Collection[str] | None = None
) -> list[JournalRow]:
    rows: dict[str, JournalRow] = {}
    for path in journal_files(dataset):
        span = file_span(path)
        if span is None or span[0] > end + PAD or span[1] < start - PAD:
            continue
        low = locate(path, start - PAD)[0]
        high = locate(path, end + PAD)[1]
        with path.open("rb") as handle:
            handle.seek(low)
            if low:
                handle.readline()
            chunk = handle.read(max(high - handle.tell(), 0)) + handle.readline()
        for line in chunk.decode("utf-8", errors="ignore").splitlines():
            fields = _fields(line)
            if len(fields) < 6 or (channels is not None and fields[1].strip() not in channels):
                continue
            row = _row(fields)
            if row is not None and start <= row.ts < end:
                rows.setdefault(row.event_id, row)
    return sorted(rows.values(), key=lambda row: (row.ts, row.event_id))
