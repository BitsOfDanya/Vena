import logging
import ssl
from typing import Any, Self
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Action, Equipment
from app.domain import actions as action_service
from app.domain import audit
from app.domain.predictions import get_prediction_source

logger = logging.getLogger(__name__)

PENDING = "pending"
CLOSED = "closed"
BATCH = 200
STATUS_LABELS = {
    "new": "зарегистрирована",
    "accepted": "принята",
    "in_progress": "в работе",
    "closed": "закрыта",
}
PRIORITY_LABELS = {"high": "высокий", "medium": "средний", "low": "низкий"}
KIND_LABELS = {
    "inspect": "Осмотр",
    "electrical diagnostic": "Электродиагностика",
    "service": "Обслуживание",
    "verify": "Проверка",
}


class Ticket(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=32)


class HelpdeskClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        url = urlsplit(settings.helpdesk_url)
        if (
            not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
            or (
                url.scheme != "https"
                and not (url.scheme == "http" and settings.helpdesk_allow_http)
            )
        ):
            raise ValueError("Задайте HTTPS-адрес системы заявок на сервере.")
        headers = {"Accept": "application/json"}
        token = settings.helpdesk_token.get_secret_value()
        if token:
            headers["Authorization"] = "Bearer " + token
        self._client = httpx.Client(
            base_url=settings.helpdesk_url.rstrip("/"),
            headers=headers,
            timeout=httpx.Timeout(5, connect=2),
            verify=ssl.create_default_context(cafile=settings.helpdesk_ca_file),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self._client.close()

    def create(self, payload: dict[str, Any]) -> Ticket:
        return self._ticket(self._client.post("/tickets", json=payload))

    def get(self, ticket_id: str) -> Ticket:
        return self._ticket(self._client.get("/tickets/" + quote(ticket_id, safe="")))

    @staticmethod
    def _ticket(response: httpx.Response) -> Ticket:
        response.raise_for_status()
        return Ticket.model_validate_json(response.content)


def _payload(session: Session, settings: Settings, action: Action) -> dict[str, Any]:
    name = object_id = None
    equipment = session.get(Equipment, action.asset_id)
    if equipment is not None:
        name, object_id = equipment.name, equipment.object_id
    else:
        source = get_prediction_source(settings)
        prediction = source.latest_for_asset(action.asset_id) if source.available else None
        if prediction is not None:
            name, object_id = prediction.name, prediction.object_id
    due = action.recommended_at.astimezone(ZoneInfo(settings.timezone))
    description = [
        f"Работа {action.id} из VENA.",
        f"Причина: {action.reason or 'не указана'}",
        f"Объект: {object_id or 'не указан'}",
        f"Канал: {action.asset_id}" + (f" — {name}" if name else ""),
        f"Приоритет: {PRIORITY_LABELS.get(action.priority, action.priority)}",
        f"Срок: {due:%d.%m.%Y %H:%M}",
    ]
    return {
        "external_ref": action.id,
        "title": f"{KIND_LABELS.get(action.kind, action.kind)}: {name or action.asset_id}",
        "description": "\n".join(description),
        "priority": action.priority,
        "due_at": action.recommended_at.isoformat(),
    }


def _apply(session: Session, action: Action, ticket: Ticket) -> bool:
    if action.helpdesk_ticket_id == ticket.id and action.helpdesk_status == ticket.status:
        return False
    action.helpdesk_ticket_id = ticket.id
    action.helpdesk_status = ticket.status
    label = STATUS_LABELS.get(ticket.status, ticket.status)
    action_service.record(session, action, "ticket", "helpdesk", f"Заявка №{ticket.id}: {label}")
    return True


def _create(session: Session, settings: Settings, client: HelpdeskClient, action: Action) -> None:
    ticket = client.create(_payload(session, settings, action))
    _apply(session, action, ticket)
    audit.record(
        session,
        actor="system",
        role="admin",
        action="helpdesk.ticket",
        resource_type="action",
        resource_id=action.id,
        detail=f"Заявка №{ticket.id}",
    )


def submit(session: Session, settings: Settings, action: Action) -> None:
    if not settings.helpdesk_url or action.helpdesk_ticket_id:
        return
    action.helpdesk_status = PENDING
    try:
        with HelpdeskClient(settings) as client:
            _create(session, settings, client, action)
    except (httpx.HTTPError, OSError, ValueError) as error:
        logger.warning("Ticket for %s will be retried by the scheduler: %s", action.id, error)
    session.flush()


def _locked(session: Session, *conditions: ColumnElement[bool]) -> list[Action]:
    statement = (
        select(Action)
        .where(*conditions)
        .order_by(Action.created_at)
        .limit(BATCH)
        .with_for_update(skip_locked=True)
    )
    return list(session.scalars(statement))


def synchronize(session: Session, settings: Settings) -> dict[str, int]:
    counts = {"created": 0, "updated": 0, "failed": 0}
    try:
        with HelpdeskClient(settings) as client:
            tracked = _locked(
                session, Action.helpdesk_ticket_id.is_not(None), Action.helpdesk_status != CLOSED
            )
            for action in tracked:
                try:
                    if _apply(session, action, client.get(action.helpdesk_ticket_id or "")):
                        counts["updated"] += 1
                except (httpx.HTTPStatusError, ValueError) as error:
                    counts["failed"] += 1
                    logger.warning("Ticket of %s was not refreshed: %s", action.id, error)
            for action in _locked(session, Action.helpdesk_status == PENDING):
                try:
                    _create(session, settings, client, action)
                    counts["created"] += 1
                except (httpx.HTTPStatusError, ValueError) as error:
                    counts["failed"] += 1
                    logger.warning("Ticket for %s was not created: %s", action.id, error)
    except (httpx.HTTPError, OSError, ValueError) as error:
        counts["failed"] += 1
        logger.warning("Help desk is unavailable, retrying on the next run: %s", error)
    session.flush()
    return counts
