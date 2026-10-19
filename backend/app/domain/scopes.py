import re
from collections.abc import Collection, Iterable
from functools import cached_property
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy import ColumnElement, String, any_, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from app.core.config import SCOPE_PATTERN, Settings, get_settings
from app.core.security import Principal, get_principal
from app.db.models import Equipment
from app.db.session import get_session
from app.domain import journal_tail
from app.domain.hierarchy import Hierarchy, load
from app.domain.predictions import get_prediction_source

ALL = "all"
KIND_LABELS = {"district": "район", "complex": "комплекс", "object": "объект"}


def among(column: Any, values: Collection[str]) -> ColumnElement[bool]:
    return column == any_(literal(sorted(values), ARRAY(String)))


def normalize(scopes: Iterable[str]) -> list[str]:
    result = list(dict.fromkeys(item.strip() for item in scopes if item and item.strip()))
    invalid = [item for item in result if not re.fullmatch(SCOPE_PATTERN, item)]
    if invalid:
        raise ValueError("Некорректная область видимости: " + ", ".join(invalid))
    return [ALL] if ALL in result else result


def resolve(scopes: Iterable[str], hierarchy: Hierarchy) -> frozenset[str] | None:
    objects: set[str] = set()
    for scope in scopes:
        kind, _, node_id = scope.partition(":")
        if kind == ALL:
            return None
        objects |= {node_id} if kind == "object" else hierarchy.under(node_id)
    return frozenset(objects)


def label(scopes: Iterable[str], hierarchy: Hierarchy, role: str = "") -> str:
    items = list(scopes)
    if role == "admin" or ALL in items:
        return "Все объекты"
    if not items:
        return "Нет доступа к объектам"
    names = []
    for scope in items:
        kind, _, node_id = scope.partition(":")
        names.append(hierarchy.name(node_id) or f"{KIND_LABELS.get(kind, kind)} {node_id}")
    return ", ".join(names[:3]) + (f" и ещё {len(names) - 3}" if len(names) > 3 else "")


class Scope:
    def __init__(
        self,
        objects: frozenset[str] | None,
        session: Session | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.objects = objects
        self._session = session
        self._settings = settings

    @property
    def unrestricted(self) -> bool:
        return self.objects is None

    def has_object(self, object_id: str | None) -> bool:
        return self.objects is None or (object_id is not None and object_id in self.objects)

    @cached_property
    def channels(self) -> frozenset[str] | None:
        if self.objects is None:
            return None
        objects = self.objects
        found: set[str] = set()
        if self._session is not None and objects:
            found.update(
                self._session.scalars(
                    select(Equipment.asset_id).where(among(Equipment.object_id, objects))
                )
            )
        if self._settings is not None and objects:
            source = get_prediction_source(self._settings)
            if source.available:
                found.update(item.asset_id for item in source.all() if item.object_id in objects)
            if self._settings.dataset_dir is not None:
                reference = journal_tail.reference(self._settings.dataset_dir)
                found.update(channel for channel, (_, obj) in reference.items() if obj in objects)
        return frozenset(found)

    def has_channel(self, asset_id: str | None) -> bool:
        channels = self.channels
        return channels is None or (asset_id is not None and asset_id in channels)


EVERYTHING = Scope(None)


def scope_for(principal: Principal, settings: Settings, session: Session | None = None) -> Scope:
    if principal.role == "admin" or ALL in principal.scopes:
        return EVERYTHING
    return Scope(resolve(principal.scopes, load(settings)), session, settings)


def get_scope(
    principal: Annotated[Principal, Depends(get_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
    session: Annotated[Session, Depends(get_session)],
) -> Scope:
    return scope_for(principal, settings, session)


ScopeDep = Annotated[Scope, Depends(get_scope)]
