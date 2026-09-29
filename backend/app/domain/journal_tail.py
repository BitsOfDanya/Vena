import csv
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BYTES_PER_HOUR = 400_000
MAX_BYTES = 64_000_000
FAULT_STATES = {"неисправен", "обесточен", "затоплен", "отключено устройство"}
STATES = "справочник_состояний.csv"
REFERENCE = "справочник_каналов_датчиков.csv"


def journal_files(dataset: Path) -> list[Path]:
    return sorted(
        [*dataset.glob("ext-journal-*.csv"), *dataset.glob("uploads/ext-journal-*.csv")],
        key=lambda path: (path.name, path.stat().st_mtime),
    )


def notable(value: str, alarm: bool, alarm_states: set[str]) -> bool:
    text = value.strip().lower()
    return alarm or text in FAULT_STATES or text in alarm_states


@lru_cache(maxsize=4)
def _alarm_states(path: str, mtime: float) -> frozenset[str]:
    with open(path, encoding="utf-8", newline="") as handle:
        return frozenset(
            (row.get("название_состояния") or "").strip().lower()
            for row in csv.DictReader(handle)
            if (row.get("тревожное") or "").strip().lower() == "true"
        )


def alarm_states(dataset: Path) -> set[str]:
    path = dataset / STATES
    if not path.is_file():
        return set()
    return set(_alarm_states(str(path), path.stat().st_mtime))


@lru_cache(maxsize=4)
def _reference(path: str, mtime: float) -> dict[str, tuple[str, str | None]]:
    result: dict[str, tuple[str, str | None]] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            channel = (row.get("ид_канала_данных") or "").strip()
            if channel:
                result[channel] = (
                    (row.get("название_датчика") or channel).strip(),
                    (row.get("ид_объект") or "").strip() or None,
                )
    return result


def reference(dataset: Path) -> dict[str, tuple[str, str | None]]:
    path = dataset / REFERENCE
    if not path.is_file():
        return {}
    return _reference(str(path), path.stat().st_mtime)


@lru_cache(maxsize=16)
def _tail(
    path: str, size: int, mtime: float, hours: int
) -> tuple[tuple[str, str, datetime, str, bool], ...]:
    budget = min(size, MAX_BYTES, max(BYTES_PER_HOUR * hours, 2_000_000))
    with open(path, "rb") as handle:
        handle.seek(size - budget)
        chunk = handle.read(budget).decode("utf-8", errors="ignore")
    lines = chunk.splitlines()
    if budget < size and lines:
        lines = lines[1:]
    rows = []
    for line in csv.reader(lines):
        if len(line) < 6 or line[0] == "ид_события":
            continue
        try:
            ts = datetime.strptime(f"{line[2]} {line[3]}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        rows.append((line[0], line[1], ts, line[5], line[4].strip().lower() in {"t", "true", "1"}))
    return tuple(rows)


def recent(
    dataset: Path, hours: int, limit: int, channel_id: str | None, timezone: str
) -> dict[str, Any]:
    files = journal_files(dataset)
    empty: dict[str, Any] = {
        "latest_at": None,
        "from": None,
        "items": [],
        "has_more": False,
        "source": "journal_file",
    }
    if not files:
        return empty
    path = files[-1]
    stat = path.stat()
    rows = _tail(str(path), stat.st_size, stat.st_mtime, hours)
    if not rows:
        return empty
    zone = ZoneInfo(timezone)
    latest = max(row[2] for row in rows)
    start = latest - timedelta(hours=hours)
    names = reference(dataset)
    flagged = alarm_states(dataset)
    selected = [
        row
        for row in rows
        if row[2] >= start
        and (channel_id is None or row[1] == channel_id)
        and notable(row[3], row[4], flagged)
    ]
    selected.sort(key=lambda row: (row[2], row[0]), reverse=True)
    return {
        "latest_at": latest.replace(tzinfo=zone),
        "from": start.replace(tzinfo=zone),
        "has_more": len(selected) > limit,
        "source": "journal_file",
        "items": [
            {
                "event_id": event_id,
                "channel_id": channel,
                "ts": ts.replace(tzinfo=zone),
                "value": value,
                "alarm": alarm,
                "name": names.get(channel, (channel, None))[0],
                "object_id": names.get(channel, (channel, None))[1],
            }
            for event_id, channel, ts, value, alarm in selected[:limit]
        ],
    }
