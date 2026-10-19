import json
import os
import secrets
import threading
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

STATUS_LABELS = {
    "new": "Зарегистрирована",
    "accepted": "Принята",
    "in_progress": "В работе",
    "closed": "Закрыта",
}
FIXTURE = Path(__file__).with_name("fixtures") / "equipment.json"
Status = Literal["new", "accepted", "in_progress", "closed"]


class TicketIn(BaseModel):
    external_ref: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=10_000)
    priority: Literal["high", "medium", "low"] = "medium"
    due_at: datetime | None = None


def create_app(
    env: Mapping[str, str] = os.environ, clock: Callable[[], float] = time.time
) -> FastAPI:
    stages = [
        ("closed", float(env.get("HELPDESK_CLOSE_SECONDS", "600"))),
        ("in_progress", float(env.get("HELPDESK_START_SECONDS", "180"))),
        ("accepted", float(env.get("HELPDESK_ACCEPT_SECONDS", "60"))),
    ]
    token = env.get("HELPDESK_TOKEN", "")
    data_file = Path(env["HELPDESK_DATA_FILE"]) if env.get("HELPDESK_DATA_FILE") else None
    registry = json.loads(Path(env.get("HELPDESK_EQUIPMENT_FILE", FIXTURE)).read_text("utf-8"))
    tickets: list[dict[str, Any]] = (
        json.loads(data_file.read_text("utf-8")) if data_file and data_file.exists() else []
    )
    lock = threading.Lock()

    def authorize(authorization: Annotated[str, Header()] = "") -> None:
        if token and not secrets.compare_digest(authorization, "Bearer " + token):
            raise HTTPException(401, "Неверный токен доступа")

    def save() -> None:
        if data_file is not None:
            temporary = data_file.with_suffix(".tmp")
            temporary.write_text(json.dumps(tickets, ensure_ascii=False), "utf-8")
            temporary.replace(data_file)

    def view(ticket: dict[str, Any]) -> dict[str, Any]:
        elapsed = clock() - ticket["created_at"]
        state = next((name for name, after in stages if elapsed >= after), "new")
        created = datetime.fromtimestamp(ticket["created_at"], UTC).isoformat()
        return {
            **ticket,
            "created_at": created,
            "status": state,
            "status_label": STATUS_LABELS[state],
        }

    api = APIRouter(dependencies=[Depends(authorize)])

    @api.post("/tickets", status_code=201)
    def create_ticket(body: TicketIn, response: Response) -> dict[str, Any]:
        with lock:
            for ticket in tickets:
                if ticket["external_ref"] == body.external_ref:
                    response.status_code = 200
                    return view(ticket)
            ticket = {"id": len(tickets) + 1, **body.model_dump(mode="json"), "created_at": clock()}
            tickets.append(ticket)
            save()
        return view(ticket)

    @api.get("/tickets/{ticket_id}")
    def read_ticket(ticket_id: int) -> dict[str, Any]:
        if not 1 <= ticket_id <= len(tickets):
            raise HTTPException(404, "Заявка не найдена")
        return view(tickets[ticket_id - 1])

    @api.get("/tickets")
    def list_tickets(
        status: Annotated[Status | None, Query()] = None,
    ) -> list[dict[str, Any]]:
        items = [view(ticket) for ticket in tickets]
        return [item for item in items if status in (None, item["status"])]

    @api.get("/equipment")
    def equipment(
        cursor: Annotated[str, Query(pattern=r"^\d{1,9}$")] = "0",
        limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    ) -> dict[str, Any]:
        offset = int(cursor)
        following = offset + limit
        return {
            "items": registry[offset:following],
            "next_cursor": str(following) if following < len(registry) else None,
        }

    app = FastAPI(title="Эмулятор системы заявок и учёта оборудования")
    app.include_router(api)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
