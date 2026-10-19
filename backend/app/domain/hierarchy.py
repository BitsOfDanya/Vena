import csv
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import Settings
from app.domain.incidents import set_object_names
from app.schemas.objects import ComplexNode, DistrictNode, ObjectLeaf, ObjectTree

FILE = "справочник_объектов_диспетчер.csv"
HEADERS = {
    "ид_объект": "id",
    "иерархия_уровень": "level",
    "родитель": "parent",
    "вид_объекта": "kind",
    "диспетчерское_название_объекта": "name",
}


@dataclass(frozen=True)
class Node:
    id: str
    level: int
    parent: str | None
    kind: str
    name: str


class Hierarchy:
    def __init__(self, nodes: Iterable[Node] = ()) -> None:
        self.nodes = {node.id: node for node in nodes}
        self.children: dict[str, list[str]] = {}
        for node in self.nodes.values():
            if node.parent and node.parent != node.id:
                self.children.setdefault(node.parent, []).append(node.id)

    def name(self, node_id: str | None) -> str | None:
        node = self.nodes.get(node_id or "")
        return node.name if node else None

    def under(self, node_id: str) -> set[str]:
        result = {node_id}
        stack = [node_id]
        while stack:
            for child in self.children.get(stack.pop(), []):
                if child not in result:
                    result.add(child)
                    stack.append(child)
        return result

    def level(self, level: int) -> list[Node]:
        return sorted(
            (node for node in self.nodes.values() if node.level == level),
            key=lambda node: (node.name.casefold(), node.id),
        )


EMPTY = Hierarchy()


def _text(value: object) -> str:
    return str(value if value is not None else "").strip()


def parse(rows: Iterable[dict]) -> Hierarchy:
    nodes = []
    for row in rows:
        values = {HEADERS.get(str(key).strip(), str(key).strip()): row[key] for key in row if key}
        node_id, name = _text(values.get("id")), _text(values.get("name"))
        try:
            level = int(_text(values.get("level")))
        except ValueError:
            continue
        if node_id and name and level in (1, 2, 3):
            parent = _text(values.get("parent")) or None
            nodes.append(Node(node_id, level, parent, _text(values.get("kind")), name))
    return Hierarchy(nodes)


def build_tree(
    hierarchy: Hierarchy, counts: Mapping[str, int], allowed: Collection[str] | None
) -> ObjectTree:
    def leaf(node_id: str) -> ObjectLeaf:
        node = hierarchy.nodes.get(node_id)
        return ObjectLeaf(
            id=node_id,
            name=node.name if node else f"Объект {node_id}",
            kind=node.kind if node else "",
            channels=counts.get(node_id, 0),
        )

    placed: set[str] = set()
    complexes: dict[str, list[ComplexNode]] = {}
    for item in hierarchy.level(2):
        members = [
            hierarchy.nodes[child]
            for child in hierarchy.children.get(item.id, [])
            if hierarchy.nodes[child].level == 3 and (allowed is None or child in allowed)
        ]
        if allowed is not None and not members:
            continue
        objects = [leaf(node.id) for node in sorted(members, key=lambda n: n.name.casefold())]
        placed.update(node.id for node in members)
        parent = hierarchy.nodes.get(item.parent or "")
        complexes.setdefault(parent.id if parent and parent.level == 1 else "", []).append(
            ComplexNode(
                id=item.id,
                name=item.name,
                channels=sum(node.channels for node in objects),
                objects=objects,
            )
        )
    districts = [
        DistrictNode(
            id=item.id,
            name=item.name,
            channels=sum(node.channels for node in complexes.get(item.id, [])),
            complexes=complexes.get(item.id, []),
        )
        for item in [*hierarchy.level(1), Node("", 1, None, "", "Без района")]
        if complexes.get(item.id) or (allowed is None and item.id)
    ]
    candidates = set(counts) | {node.id for node in hierarchy.level(3)}
    unassigned = [
        leaf(node_id)
        for node_id in sorted(candidates - placed)
        if (allowed is None or node_id in allowed)
        and (node_id not in hierarchy.nodes or hierarchy.nodes[node_id].level == 3)
    ]
    return ObjectTree(available=bool(hierarchy.nodes), districts=districts, unassigned=unassigned)


@lru_cache(maxsize=4)
def _read(path: str, mtime: float) -> Hierarchy:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return parse(csv.DictReader(handle))


_current: Hierarchy | None = None


def load(settings: Settings) -> Hierarchy:
    global _current
    hierarchy = EMPTY
    if settings.dataset_dir is not None:
        path = settings.dataset_dir / FILE
        try:
            hierarchy = _read(str(path), path.stat().st_mtime)
        except (OSError, UnicodeError, csv.Error):
            hierarchy = EMPTY
    if hierarchy is not _current:
        _current = hierarchy
        set_object_names({node.id: node.name for node in hierarchy.nodes.values()})
    return hierarchy
