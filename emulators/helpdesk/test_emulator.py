import json

from fastapi.testclient import TestClient

from emulator import FIXTURE, create_app

TICKET = {
    "external_ref": "A-1101",
    "title": "Осмотр: Насос P-0142",
    "description": "Причина: рост частоты отказов",
    "priority": "high",
}


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def test_ticket_status_progresses_over_time() -> None:
    clock = Clock()
    env = {
        "HELPDESK_ACCEPT_SECONDS": "60",
        "HELPDESK_START_SECONDS": "180",
        "HELPDESK_CLOSE_SECONDS": "600",
    }
    client = TestClient(create_app(env, clock))
    created = client.post("/tickets", json=TICKET)
    assert created.status_code == 201
    ticket = created.json()
    assert (ticket["id"], ticket["status"]) == (1, "new")

    seen = []
    for elapsed in [59, 60, 179, 180, 599, 600, 3600]:
        clock.now = 1_000_000.0 + elapsed
        body = client.get("/tickets/1").json()
        seen.append((body["status"], body["status_label"]))
    assert seen == [
        ("new", "Зарегистрирована"),
        ("accepted", "Принята"),
        ("accepted", "Принята"),
        ("in_progress", "В работе"),
        ("in_progress", "В работе"),
        ("closed", "Закрыта"),
        ("closed", "Закрыта"),
    ]
    closed = client.get("/tickets", params={"status": "closed"}).json()
    assert [item["id"] for item in closed] == [1]
    assert client.get("/tickets", params={"status": "new"}).json() == []


def test_external_ref_is_idempotent_and_validated() -> None:
    client = TestClient(create_app({}, Clock()))
    first = client.post("/tickets", json=TICKET)
    again = client.post("/tickets", json={**TICKET, "title": "Повтор"})
    other = client.post("/tickets", json={**TICKET, "external_ref": "A-1102"})
    assert (first.status_code, again.status_code, other.status_code) == (201, 200, 201)
    assert again.json()["id"] == first.json()["id"] and again.json()["title"] == TICKET["title"]
    assert other.json()["id"] == 2
    assert client.get("/tickets/3").status_code == 404
    assert client.post("/tickets", json={**TICKET, "priority": "urgent"}).status_code == 422
    assert client.post("/tickets", json={"title": "Без ссылки"}).status_code == 422


def test_token_is_required_when_configured() -> None:
    client = TestClient(create_app({"HELPDESK_TOKEN": "secret-token"}, Clock()))
    assert client.post("/tickets", json=TICKET).status_code == 401
    assert client.get("/equipment", headers={"Authorization": "Bearer wrong"}).status_code == 401
    headers = {"Authorization": "Bearer secret-token"}
    assert client.post("/tickets", json=TICKET, headers=headers).status_code == 201
    assert client.get("/health").json() == {"status": "ok"}


def test_tickets_survive_restart(tmp_path) -> None:
    env = {"HELPDESK_DATA_FILE": str(tmp_path / "tickets.json")}
    TestClient(create_app(env, Clock())).post("/tickets", json=TICKET)
    restarted = TestClient(create_app(env, Clock()))
    assert restarted.get("/tickets/1").json()["external_ref"] == "A-1101"
    assert restarted.post("/tickets", json=TICKET).status_code == 200


def test_equipment_registry_is_paginated_by_cursor() -> None:
    client = TestClient(create_app({}, Clock()))
    registry = json.loads(FIXTURE.read_text("utf-8"))
    items, cursor, pages = [], None, 0
    while True:
        params = {"limit": 5} | ({"cursor": cursor} if cursor else {})
        page = client.get("/equipment", params=params).json()
        items += page["items"]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert items == registry and pages == 4
    assert client.get("/equipment").json()["next_cursor"] is None
    assert client.get("/equipment", params={"cursor": "abc"}).status_code == 422
