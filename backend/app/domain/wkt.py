import math
import re
from typing import Any

TYPES = {
    "POINT": "Point",
    "LINESTRING": "LineString",
    "POLYGON": "Polygon",
    "MULTIPOINT": "MultiPoint",
    "MULTILINESTRING": "MultiLineString",
    "MULTIPOLYGON": "MultiPolygon",
}
NAMES = {value: key for key, value in TYPES.items()}
DEPTH = {
    "Point": 0,
    "LineString": 1,
    "MultiPoint": 1,
    "Polygon": 2,
    "MultiLineString": 2,
    "MultiPolygon": 3,
}
SUPPORTED = "POINT, LINESTRING, POLYGON, MULTIPOINT, MULTILINESTRING, MULTIPOLYGON"

_TOKEN = re.compile(r"\s*(?:([A-Za-z]+)|([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)|([(),]))")
_SRID = re.compile(r"^\s*SRID\s*=\s*(\d+)\s*;", re.IGNORECASE)

Coordinates = Any


class WktError(ValueError):
    pass


def _tokens(text: str) -> list[str | float]:
    result: list[str | float] = []
    position = 0
    text = text.rstrip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if match is None or match.end() == position:
            raise WktError(f"Не удалось разобрать WKT около «{text[position : position + 20]}»")
        word, number, symbol = match.groups()
        if number is not None:
            result.append(float(number))
        else:
            result.append((word or symbol or "").upper())
        position = match.end()
    return result


def _nested(tokens: list[str | float], position: int) -> tuple[list[Any], int]:
    if position >= len(tokens) or tokens[position] != "(":
        raise WktError("Ожидалась открывающая скобка")
    position += 1
    items: list[Any] = []
    while True:
        if position >= len(tokens):
            raise WktError("Не хватает закрывающей скобки")
        if tokens[position] == "(":
            item, position = _nested(tokens, position)
        else:
            numbers: list[float] = []
            while position < len(tokens) and isinstance(tokens[position], float):
                numbers.append(float(tokens[position]))
                position += 1
            if not 2 <= len(numbers) <= 4:
                raise WktError("Каждая вершина должна содержать долготу и широту")
            item = numbers[:2]
        items.append(item)
        if position >= len(tokens):
            raise WktError("Не хватает закрывающей скобки")
        if tokens[position] == ",":
            position += 1
            continue
        if tokens[position] == ")":
            return items, position + 1
        raise WktError(f"Неожиданный элемент WKT: {tokens[position]}")


def _is_position(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and all(isinstance(item, float) for item in value)
    )


def _check_position(value: Any) -> list[float]:
    if not _is_position(value):
        raise WktError("Неверная вложенность скобок для этого типа геометрии")
    lon, lat = value
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise WktError("Координаты должны быть конечными числами")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise WktError(f"Координаты вне WGS 84: {lon} {lat}. Ожидается порядок «долгота широта»")
    return [lon, lat]


def _line(value: Any) -> list[list[float]]:
    if not isinstance(value, list):
        raise WktError("Неверная вложенность скобок для линии")
    line = [_check_position(item) for item in value]
    if len(line) < 2:
        raise WktError("Линия должна содержать не менее двух вершин")
    return line


def _ring(value: Any) -> list[list[float]]:
    ring = _line(value)
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    if len(ring) < 4:
        raise WktError("Контур полигона должен содержать не менее трёх различных вершин")
    return ring


def _polygon(value: Any) -> list[list[list[float]]]:
    if not isinstance(value, list) or not value:
        raise WktError("Полигон должен содержать внешний контур")
    return [_ring(item) for item in value]


def _geometry(kind: str, parsed: list[Any]) -> Coordinates:
    if kind == "Point":
        if len(parsed) != 1:
            raise WktError("Точка должна содержать одну вершину")
        return _check_position(parsed[0])
    if kind == "LineString":
        return _line(parsed)
    if kind == "Polygon":
        return _polygon(parsed)
    if kind == "MultiPoint":
        points = [item[0] if isinstance(item, list) and len(item) == 1 else item for item in parsed]
        return [_check_position(item) for item in points]
    if kind == "MultiLineString":
        return [_line(item) for item in parsed]
    return [_polygon(item) for item in parsed]


def parse(text: str) -> dict[str, Any]:
    srid = _SRID.match(text)
    if srid and srid.group(1) != "4326":
        raise WktError(f"Ожидается система координат EPSG:4326, получена SRID={srid.group(1)}")
    tokens = _tokens(text[srid.end() :] if srid else text)
    if not tokens or not isinstance(tokens[0], str) or tokens[0] in {"(", ")", ","}:
        raise WktError("WKT должен начинаться с типа геометрии")
    name = str(tokens[0])
    position = 1
    while position < len(tokens) and tokens[position] in {"Z", "M", "ZM"}:
        position += 1
    for suffix in ("ZM", "Z", "M"):
        if name not in TYPES and name.endswith(suffix) and name[: -len(suffix)] in TYPES:
            name = name[: -len(suffix)]
    if name not in TYPES:
        raise WktError(f"Неподдерживаемый тип WKT «{name}». Допустимы: {SUPPORTED}")
    if position < len(tokens) and tokens[position] == "EMPTY":
        raise WktError("Пустая геометрия не может быть импортирована")
    parsed, position = _nested(tokens, position)
    if position != len(tokens):
        raise WktError("Лишние символы после геометрии WKT")
    kind = TYPES[name]
    return {"type": kind, "coordinates": _geometry(kind, parsed)}


def _number(value: Any) -> str:
    return format(float(value), ".15g")


def _wrap(coordinates: Any, depth: int) -> str:
    if depth == 0:
        return f"{_number(coordinates[0])} {_number(coordinates[1])}"
    return "(" + ", ".join(_wrap(item, depth - 1) for item in coordinates) + ")"


def dumps(geometry: dict[str, Any]) -> str:
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        parts = [dumps(item) for item in geometry.get("geometries") or []]
        return f"GEOMETRYCOLLECTION ({', '.join(parts)})" if parts else "GEOMETRYCOLLECTION EMPTY"
    if kind not in NAMES:
        raise WktError(f"Тип геометрии {kind} не выгружается в WKT")
    coordinates: Any = geometry.get("coordinates")
    if kind == "Point":
        return f"POINT ({_wrap(coordinates, 0)})"
    if kind == "MultiPoint":
        return "MULTIPOINT (" + ", ".join(f"({_wrap(item, 0)})" for item in coordinates) + ")"
    return f"{NAMES[kind]} {_wrap(coordinates, DEPTH[kind])}"
