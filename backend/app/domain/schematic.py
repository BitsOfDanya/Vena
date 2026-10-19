import hashlib
import math
import random
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Equipment
from app.domain.analytics import PICKET, PICKET_METERS
from app.domain.incidents import location_group
from app.domain.predictions import PredictionSource

SOURCE = "generated"
LABEL = "Условная геометрия"
NOTE = (
    "Координаты объектов отсутствуют. Схема построена по реестру каналов и снимку прогнозов: "
    "ось коллектора с боковыми галереями, каналы расставлены по пикетам (1 ПК = 10 м). "
    "Положение на карте условное и не соответствует реальной трассе."
)
WEST, SOUTH, EAST, NORTH = 37.35, 55.57, 37.85, 55.92
METERS_PER_DEGREE = 111_320.0
MARGIN = 0.08
TAIL_M = 30.0
SPREAD_STEP_M = 25.0
MIN_LENGTH_M = 200.0
MAX_SPREAD_LENGTH_M = 3000.0
MAX_TURN_M = 900.0
WOBBLE_M = 60.0
SINGLE_GAP_M = 400.0
GALLERY_TAIL_M = 20.0
MIN_GALLERY_M = 60.0
GALLERY_OFFSET_M = 40.0

GALLERY = re.compile(
    r"(?<![А-Яа-яЁё])(?:Г|[Гг]ал)\.?\s*(\d*)\s*ПК\s*(\d+)(?:\s*\+\s*(\d+(?:[.,]\d+)?))?"
)

Point = tuple[float, float]


@dataclass(frozen=True)
class Channel:
    asset_id: str
    object_id: str
    name: str
    tag: str
    sensor_type: str


@dataclass(frozen=True)
class Mark:
    main_m: float | None = None
    main_label: str | None = None
    gallery: str | None = None
    gallery_m: float | None = None
    gallery_label: str | None = None

    @property
    def label(self) -> str | None:
        return " · ".join(part for part in (self.main_label, self.gallery_label) if part) or None


@dataclass
class Gallery:
    number: str
    branch_m: float | None
    length: float
    members: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Cell:
    west: float
    south: float
    width: float
    height: float
    meters_lon: float

    @property
    def box(self) -> tuple[float, float]:
        return self.width * (1 - 2 * MARGIN), self.height * (1 - 2 * MARGIN)

    def lonlat(self, point: Point) -> list[float]:
        x, y = point[0] + self.width * MARGIN, point[1] + self.height * MARGIN
        return [
            round(self.west + x / self.meters_lon, 6),
            round(self.south + y / METERS_PER_DEGREE, 6),
        ]


class Axis:
    def __init__(self, points: list[Point]) -> None:
        self.points = points
        self.cumulative = [0.0]
        for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
            self.cumulative.append(self.cumulative[-1] + math.hypot(x1 - x0, y1 - y0))

    @property
    def length(self) -> float:
        return self.cumulative[-1]

    def _segment(self, distance: float) -> int:
        index = 1
        while index < len(self.points) - 1 and self.cumulative[index] < distance:
            index += 1
        return index

    def _tangent(self, index: int) -> Point:
        (x0, y0), (x1, y1) = self.points[index - 1], self.points[index]
        span = math.hypot(x1 - x0, y1 - y0) or 1.0
        return (x1 - x0) / span, (y1 - y0) / span

    def at(self, distance: float) -> tuple[Point, Point]:
        distance = min(max(distance, 0.0), self.length)
        index = self._segment(distance)
        (x0, y0), (x1, y1) = self.points[index - 1], self.points[index]
        span = self.cumulative[index] - self.cumulative[index - 1] or 1.0
        share = (distance - self.cumulative[index - 1]) / span
        return (x0 + (x1 - x0) * share, y0 + (y1 - y0) * share), self._tangent(index)

    def offset(self, distance: float, shift: float) -> Point:
        (x, y), (tx, ty) = self.at(distance)
        nx, ny = -ty, tx
        index = self._segment(distance)
        if index < len(self.points) - 1 and abs(self.cumulative[index] - distance) < 1e-6:
            ax, ay = self._tangent(index)
            bx, by = self._tangent(index + 1)
            mx, my = -(ay + by), ax + bx
            norm = math.hypot(mx, my)
            if norm > 1e-6:
                mx, my = mx / norm, my / norm
                scale = 1 / max(mx * -ay + my * ax, 0.3)
                nx, ny = mx * scale, my * scale
        return x + nx * shift, y + ny * shift


def _digest(*parts: str) -> int:
    return int.from_bytes(hashlib.sha256(":".join(("vena", *parts)).encode()).digest()[:8], "big")


def _meters(whole: str, extra: str | None) -> float:
    return int(whole) * PICKET_METERS + (float(extra.replace(",", ".")) if extra else 0.0)


def _picket_text(whole: str, extra: str | None) -> str:
    return f"ПК{int(whole)}" + (f"+{extra}" if extra else "")


def mark(name: str) -> Mark:
    text = name or ""
    gallery = GALLERY.search(text)
    main = PICKET.search(text[: gallery.start()] if gallery else text)
    result = Mark()
    if main:
        result = Mark(
            main_m=_meters(main.group(1), main.group(2)),
            main_label=_picket_text(main.group(1), main.group(2)),
        )
    if gallery:
        number, whole, extra = gallery.groups()
        prefix = f"Г{int(number)}" if number else "Гал."
        result = Mark(
            main_m=result.main_m,
            main_label=result.main_label,
            gallery=str(int(number)) if number else "",
            gallery_m=_meters(whole, extra),
            gallery_label=f"{prefix} {_picket_text(whole, extra)}",
        )
    return result


def collect_channels(session: Session, source: PredictionSource) -> list[Channel]:
    channels: dict[str, Channel] = {}
    for row in session.scalars(select(Equipment).where(Equipment.status != "retired")):
        if row.object_id:
            channels[row.asset_id] = Channel(
                row.asset_id, row.object_id, row.name, row.tag, row.equipment_type
            )
    for prediction in source.all() if source.available else []:
        if prediction.asset_id in channels or not prediction.object_id:
            continue
        channels[prediction.asset_id] = Channel(
            prediction.asset_id,
            prediction.object_id,
            prediction.name or "",
            prediction.location_tag or "",
            prediction.sensor_type or "",
        )
    return list(channels.values())


def _serpentine(
    length: float, width: float, height: float, rng: random.Random
) -> tuple[list[Point], float | None]:
    along_x = rng.random() < 0.5
    long_side, short_side = (width, height) if along_x else (height, width)
    legs = max(1, math.ceil(length / (long_side * 0.9)))
    gap = min(short_side * 0.8 / legs, MAX_TURN_M)
    leg = (length - (legs - 1) * gap) / legs
    pieces = max(2, round(leg / 700))
    wobble = min(gap * 0.15, WOBBLE_M, leg / pieces * 0.08)
    points: list[Point] = []
    for index in range(legs):
        stops = [leg * step / pieces for step in range(pieces + 1)]
        if index % 2:
            stops.reverse()
        for number, along in enumerate(stops):
            shift = rng.uniform(-wobble, wobble) if 0 < number < pieces else 0.0
            points.append((along, index * gap + shift))
    if not along_x:
        points = [(y, x) for x, y in points]
    return points, gap if legs > 1 else None


def _rotate(points: list[Point], angle: float) -> list[Point]:
    cx = sum(x for x, _ in points) / len(points)
    cy = sum(y for _, y in points) / len(points)
    cos, sin = math.cos(angle), math.sin(angle)
    return [
        (cx + (x - cx) * cos - (y - cy) * sin, cy + (x - cx) * sin + (y - cy) * cos)
        for x, y in points
    ]


def _bounds(points: list[Point]) -> tuple[float, float, float, float]:
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _place(
    points: list[Point], width: float, height: float, straight: bool, rng: random.Random
) -> list[Point]:
    angle = rng.uniform(-1, 1) * math.radians(50 if straight else 15)
    shape = points
    for factor in (1.0, 0.5):
        candidate = _rotate(points, angle * factor)
        x0, y0, x1, y1 = _bounds(candidate)
        if x1 - x0 <= width and y1 - y0 <= height:
            shape = candidate
            break
    x0, y0, x1, y1 = _bounds(shape)
    dx = rng.uniform(0, max(width - (x1 - x0), 0.0)) - x0
    dy = rng.uniform(0, max(height - (y1 - y0), 0.0)) - y0
    return [(x + dx, y + dy) for x, y in shape]


def _gallery_line(axis: Axis, distance: float, length: float, shift: float) -> list[Point]:
    branch, _ = axis.at(distance)
    stub = abs(shift)
    if length <= stub:
        end = axis.offset(distance, math.copysign(length, shift))
        return [branch, end]
    points = [branch, axis.offset(distance, shift)]
    direction = 1 if axis.length - distance >= distance else -1
    target = min(max(distance + direction * (length - stub), 0.0), axis.length)
    stops = sorted(
        (
            value
            for value in axis.cumulative[1:-1]
            if min(distance, target) < value < max(distance, target)
        ),
        reverse=direction < 0,
    )
    points.extend(axis.offset(value, shift) for value in [*stops, target])
    deficit = length - Axis(points).length
    if deficit > 0:
        (x0, y0), (x1, y1) = points[-2], points[-1]
        span = math.hypot(x1 - x0, y1 - y0) or 1.0
        points[-1] = (x1 + (x1 - x0) / span * deficit, y1 + (y1 - y0) / span * deficit)
    return points


def _gallery_specs(
    members: list[Channel], marks: dict[str, Mark], rng: random.Random
) -> list[Gallery]:
    groups: dict[str, list[str]] = {}
    for item in members:
        current = marks[item.asset_id]
        if current.gallery is None:
            continue
        key = current.gallery or f"@{current.main_m}"
        groups.setdefault(key, []).append(item.asset_id)
    specs = []
    for key in sorted(groups, key=lambda value: (value.startswith("@"), value.zfill(6))):
        ids = groups[key]
        branches = Counter(
            marks[asset_id].main_m for asset_id in ids if marks[asset_id].main_m is not None
        )
        branch = min(branches, key=lambda value: (-branches[value], value)) if branches else None
        reach = max(marks[asset_id].gallery_m or 0.0 for asset_id in ids)
        specs.append(
            Gallery(
                number=marks[ids[0]].gallery or "",
                branch_m=branch,
                length=max(reach + GALLERY_TAIL_M, MIN_GALLERY_M),
                members=ids,
            )
        )
    if not specs:
        specs = [
            Gallery(number="", branch_m=None, length=rng.uniform(60, 180))
            for _ in range(1 + rng.randrange(3))
        ]
    return specs


def _picket_number(meters: float) -> int:
    return round(meters / PICKET_METERS)


def _line(cell: Cell, points: list[Point]) -> dict[str, Any]:
    return {"type": "MultiLineString", "coordinates": [[cell.lonlat(point) for point in points]]}


def _extent(marks: dict[str, Mark]) -> tuple[float, float]:
    known = [value.main_m for value in marks.values() if value.main_m is not None]
    if not known:
        return 0.0, min(max(MIN_LENGTH_M, SPREAD_STEP_M * len(marks)), MAX_SPREAD_LENGTH_M)
    start = max(0.0, math.floor((min(known) - TAIL_M) / PICKET_METERS) * PICKET_METERS)
    return start, max(max(known) - start + TAIL_M, MIN_LENGTH_M)


def _object_features(object_id: str, members: list[Channel], cell: Cell) -> list[dict[str, Any]]:
    rng = random.Random(_digest("object", object_id))
    members = sorted(members, key=lambda item: item.asset_id)
    marks = {item.asset_id: mark(item.name) for item in members}
    specs = _gallery_specs(members, marks, rng)
    start, length = _extent(marks)
    width, height = cell.box
    raw, gap = _serpentine(length, width, height, rng)
    axis = Axis(_place(raw, width, height, gap is None, rng))
    spacing = gap or SINGLE_GAP_M
    collector_id = f"collector-{object_id}"
    common = {"object_id": object_id, "group_id": object_id, "source": SOURCE}
    features: list[dict[str, Any]] = [
        {
            "type": "Feature",
            "id": collector_id,
            "geometry": _line(cell, axis.points),
            "properties": {
                "kind": "collector",
                **common,
                "name": f"Коллектор объекта {object_id}",
                "label": LABEL,
                "length_m": round(axis.length),
                "picket_from": _picket_number(start),
                "picket_to": math.ceil((start + axis.length) / PICKET_METERS),
                "channel_count": len(members),
                "gallery_count": len(specs),
            },
        }
    ]
    placed: dict[str, tuple[Point, str, float, str | None]] = {}
    floating = sum(1 for spec in specs if spec.branch_m is None)
    slot = 0
    side = rng.choice((1, -1))
    for index, spec in enumerate(specs):
        if spec.branch_m is None:
            distance = axis.length * (slot + rng.uniform(0.3, 0.7)) / floating
            slot += 1
        else:
            distance = spec.branch_m - start
        shift = min(GALLERY_OFFSET_M + 20 * (index % 3), spacing * 0.4) * side * (-1) ** index
        line = Axis(_gallery_line(axis, distance, spec.length, shift))
        gallery_id = f"gallery-{object_id}-{index + 1}"
        branch = _picket_number(start + distance)
        title = f"Галерея Г{spec.number}" if spec.number else "Боковая галерея"
        features.append(
            {
                "type": "Feature",
                "id": gallery_id,
                "geometry": _line(cell, line.points),
                "properties": {
                    "kind": "gallery",
                    **common,
                    "collector_id": collector_id,
                    "name": f"{title} · от ПК{branch}",
                    "number": spec.number or None,
                    "picket": f"ПК{branch}",
                    "picket_m": round(start + distance, 1),
                    "length_m": round(line.length),
                    "channel_count": len(spec.members),
                    "basis": "channel_names" if spec.members else "synthetic",
                },
            }
        )
        for asset_id in spec.members:
            chainage = marks[asset_id].gallery_m or 0.0
            placed[asset_id] = (line.at(chainage)[0], "gallery", chainage, gallery_id)
    spread = [
        item.asset_id
        for item in members
        if item.asset_id not in placed and marks[item.asset_id].main_m is None
    ]
    for number, asset_id in enumerate(spread):
        distance = axis.length * (number + 1) / (len(spread) + 1)
        placed[asset_id] = (axis.at(distance)[0], "spread", start + distance, None)
    for item in members:
        main_m = marks[item.asset_id].main_m
        if item.asset_id not in placed and main_m is not None:
            placed[item.asset_id] = (axis.at(main_m - start)[0], "picket", main_m, None)
        point, placement, chainage, branch_id = placed[item.asset_id]
        features.append(
            {
                "type": "Feature",
                "id": item.asset_id,
                "geometry": {"type": "Point", "coordinates": cell.lonlat(point)},
                "properties": {
                    "kind": "asset",
                    **common,
                    "asset_id": item.asset_id,
                    "collector_id": collector_id,
                    "gallery_id": branch_id,
                    "name": item.name or item.asset_id,
                    "sensor_type": item.sensor_type or None,
                    "location_group": location_group(item.tag),
                    "picket": marks[item.asset_id].label,
                    "picket_m": round(chainage, 1),
                    "placement": placement,
                },
            }
        )
    return features


def _cells(count: int) -> list[Cell]:
    lat_mid = (SOUTH + NORTH) / 2
    width = (EAST - WEST) * METERS_PER_DEGREE * math.cos(math.radians(lat_mid))
    height = (NORTH - SOUTH) * METERS_PER_DEGREE
    cols = max(1, math.ceil(math.sqrt(count * width / height)))
    rows = max(1, math.ceil(count / cols))
    step_lon, step_lat = (EAST - WEST) / cols, (NORTH - SOUTH) / rows
    cells = []
    for index in range(count):
        south = NORTH - (index // cols + 1) * step_lat
        meters_lon = METERS_PER_DEGREE * math.cos(math.radians(south + step_lat / 2))
        cells.append(
            Cell(
                west=WEST + (index % cols) * step_lon,
                south=south,
                width=step_lon * meters_lon,
                height=step_lat * METERS_PER_DEGREE,
                meters_lon=meters_lon,
            )
        )
    return cells


def build(channels: list[Channel]) -> dict[str, Any]:
    by_object: dict[str, list[Channel]] = {}
    for channel in channels:
        by_object.setdefault(channel.object_id, []).append(channel)
    order = sorted(by_object, key=lambda object_id: (_digest(object_id), object_id))
    features: list[dict[str, Any]] = []
    for object_id, cell in zip(order, _cells(len(order)), strict=True):
        features.extend(_object_features(object_id, by_object[object_id], cell))
    rank = {"collector": 0, "gallery": 1, "asset": 2}
    features.sort(key=lambda feature: rank[feature["properties"]["kind"]])
    return {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "source": SOURCE,
            "label": LABEL,
            "crs": "EPSG:4326",
            "picket_m": PICKET_METERS,
            "object_count": len(order),
            "channel_count": len(channels),
            "note": NOTE,
        },
    }


def generate(session: Session, source: PredictionSource) -> dict[str, Any] | None:
    channels = collect_channels(session, source)
    return build(channels) if channels else None
