import json
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain import helpdesk
from app.schemas.equipment import EquipmentIn


class FakeHelpdesk:
    def __init__(self) -> None:
        self.tickets: dict[str, dict] = {}
        self.requests: list[httpx.Request] = []
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("connection refused", request=request)
        self.requests.append(request)
        if request.method == "POST" and request.url.path == "/api/tickets":
            body = json.loads(request.content)
            for ticket in self.tickets.values():
                if ticket["external_ref"] == body["external_ref"]:
                    return httpx.Response(200, json=ticket)
            ticket = {"id": len(self.tickets) + 1, "status": "new", **body}
            self.tickets[str(ticket["id"])] = ticket
            return httpx.Response(201, json=ticket)
        ticket_id = request.url.path.removeprefix("/api/tickets/")
        if request.method == "GET" and ticket_id in self.tickets:
            return httpx.Response(200, json=self.tickets[ticket_id])
        return httpx.Response(404, json={"detail": "not found"})


@pytest.fixture()
def fake(monkeypatch) -> FakeHelpdesk:
    desk = FakeHelpdesk()
    settings = get_settings()
    monkeypatch.setattr(settings, "helpdesk_url", "https://helpdesk.test/api")
    monkeypatch.setattr(settings, "helpdesk_token", SecretStr("desk-token"))
    client = partial(helpdesk.HelpdeskClient, transport=httpx.MockTransport(desk))
    monkeypatch.setattr(helpdesk, "HelpdeskClient", client)
    return desk


def _action(client: TestClient, status: str = "suggested") -> dict:
    payload = {
        "asset_id": "P-0142",
        "kind": "inspect",
        "reason": "Рост частоты отказов насоса",
        "priority": "high",
        "recommended_at": (datetime.now(tz=UTC) + timedelta(hours=24)).isoformat(),
        "status": status,
    }
    response = client.post("/api/v1/actions", json=payload)
    assert response.status_code == 201
    return response.json()


def _sync() -> dict[str, int]:
    with SessionLocal() as session:
        counts = helpdesk.synchronize(session, get_settings())
        session.commit()
    return counts


def _notes(action: dict) -> list[str]:
    return [event["note"] for event in action["history"] if event["event_type"] == "ticket"]


def test_approval_creates_ticket_with_work_details(client: TestClient, fake: FakeHelpdesk) -> None:
    from app.db.models import Equipment

    with SessionLocal.begin() as session:
        session.add(
            Equipment(
                asset_id="P-0142",
                external_id="EQ-142",
                source="customer",
                name="Насос Н1 ПК14",
                object_id="3360",
            )
        )
    draft = _action(client)
    assert draft["helpdesk_ticket_id"] is None and not fake.requests

    approved = client.post(f"/api/v1/actions/{draft['id']}/approve").json()

    assert approved["status"] == "planned"
    assert (approved["helpdesk_ticket_id"], approved["helpdesk_status"]) == ("1", "new")
    assert _notes(approved) == ["Заявка №1: зарегистрирована"]
    request = fake.requests[0]
    assert request.headers["Authorization"] == "Bearer desk-token"
    body = json.loads(request.content)
    assert body["external_ref"] == draft["id"]
    assert body["priority"] == "high"
    assert body["title"] == "Осмотр: Насос Н1 ПК14"
    for text in ["Рост частоты", "Объект: 3360", "P-0142 — Насос Н1 ПК14", "высокий", "Срок:"]:
        assert text in body["description"]
    entries = {(row["action"], row["resource_id"]) for row in client.get("/api/v1/audit").json()}
    assert ("helpdesk.ticket", draft["id"]) in entries


def test_planned_work_gets_ticket_on_creation(client: TestClient, fake: FakeHelpdesk) -> None:
    planned = _action(client, "planned")
    assert planned["helpdesk_ticket_id"] == "1"
    assert _action(client)["helpdesk_status"] is None
    assert len(fake.tickets) == 1


def test_unavailable_helpdesk_does_not_block_work(client: TestClient, fake: FakeHelpdesk) -> None:
    fake.down = True
    draft = _action(client)
    approved = client.post(f"/api/v1/actions/{draft['id']}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "planned"
    assert approved.json()["helpdesk_status"] == "pending"
    assert _sync() == {"created": 0, "updated": 0, "failed": 1}

    fake.down = False
    assert _sync()["created"] == 1
    action = client.get(f"/api/v1/actions/{draft['id']}").json()
    assert (action["helpdesk_ticket_id"], action["helpdesk_status"]) == ("1", "new")
    assert _sync() == {"created": 0, "updated": 0, "failed": 0}
    assert len(fake.tickets) == 1


def test_status_sync_records_history_without_closing_work(
    client: TestClient, fake: FakeHelpdesk
) -> None:
    action_id = _action(client, "planned")["id"]
    for status in ["accepted", "in_progress", "closed"]:
        fake.tickets["1"]["status"] = status
        assert _sync()["updated"] == 1
    assert _sync()["updated"] == 0
    polls = [request for request in fake.requests if request.method == "GET"]

    action = client.get(f"/api/v1/actions/{action_id}").json()
    assert action["status"] == "planned" and action["result_outcome"] is None
    assert action["helpdesk_status"] == "closed"
    assert _notes(action) == [
        "Заявка №1: зарегистрирована",
        "Заявка №1: принята",
        "Заявка №1: в работе",
        "Заявка №1: закрыта",
    ]
    _sync()
    assert len([request for request in fake.requests if request.method == "GET"]) == len(polls)
    completed = client.post(
        f"/api/v1/actions/{action_id}/result", json={"outcome": "maintenance_performed"}
    )
    assert completed.json()["status"] == "completed"


def test_bad_ticket_does_not_stop_sync(client: TestClient, fake: FakeHelpdesk) -> None:
    first = _action(client, "planned")["id"]
    second = _action(client, "planned")["id"]
    del fake.tickets["1"]
    fake.tickets["2"]["status"] = "accepted"
    assert _sync() == {"created": 0, "updated": 1, "failed": 1}
    assert client.get(f"/api/v1/actions/{first}").json()["helpdesk_status"] == "new"
    assert client.get(f"/api/v1/actions/{second}").json()["helpdesk_status"] == "accepted"


def test_misconfigured_helpdesk_keeps_work_pending(client: TestClient, fake, monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "helpdesk_url", "http://helpdesk.test/api")
    assert _action(client, "planned")["helpdesk_status"] == "pending"
    monkeypatch.setattr(settings, "helpdesk_allow_http", True)
    monkeypatch.setattr(settings, "helpdesk_ca_file", "/missing/customer-ca.pem")
    assert _action(client, "planned")["helpdesk_status"] == "pending"
    assert _sync()["failed"] == 1 and not fake.requests
    monkeypatch.setattr(settings, "helpdesk_ca_file", None)
    assert _sync()["created"] == 2


def test_without_helpdesk_nothing_is_sent(client: TestClient, monkeypatch) -> None:
    from app.domain.scheduler import build_scheduler

    settings = get_settings()
    assert settings.helpdesk_url == ""
    action = _action(client, "planned")
    assert action["helpdesk_ticket_id"] is None and action["helpdesk_status"] is None
    assert build_scheduler(settings).get_job("helpdesk_sync") is None
    monkeypatch.setattr(settings, "helpdesk_url", "https://helpdesk.test")
    job = build_scheduler(settings).get_job("helpdesk_sync")
    assert job is not None and job.trigger.interval.total_seconds() == 60
    status = client.get("/api/v1/integrations/status").json()
    assert status["helpdesk_configured"] is True


def test_emulator_registry_fixture_matches_sync_contract() -> None:
    fixture = Path(__file__).parents[2] / "emulators" / "helpdesk" / "fixtures" / "equipment.json"
    rows = [EquipmentIn.model_validate(item) for item in json.loads(fixture.read_text("utf-8"))]
    assert len({row.asset_id for row in rows}) == len(rows) >= 10
