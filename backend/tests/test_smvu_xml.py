import json

from fastapi.testclient import TestClient

XML = {"Content-Type": "application/xml"}


def _xml(events: str, batch_id: str = "xml-1", count: int = 2) -> str:
    header = '<?xml version="1.0" encoding="UTF-8"?>'
    return f'{header}<batch id="{batch_id}" event_count="{count}">{events}</batch>'


EVENTS = (
    '<event event_id="x1" channel_id="96463" ts="2026-07-01T09:00:00" alarm="true">'
    "Неисправен</event>"
    '<event event_id="x2" channel_id="96463" ts="2026-07-01T06:05:00+00:00">Норма</event>'
)


def test_xml_batch_is_spooled_like_json(client: TestClient, auth_users, monkeypatch, tmp_path):
    from app.core.config import get_settings
    from app.db.session import SessionLocal
    from app.domain.imports import publish_pending

    monkeypatch.setattr(get_settings(), "inbox_dir", tmp_path)
    headers = {**auth_users["dispatcher"], **XML}
    viewer = {**auth_users["viewer"], **XML}
    denied = client.post("/api/v1/smvu/events", headers=viewer, content=_xml(EVENTS))
    assert denied.status_code == 403

    accepted = client.post("/api/v1/smvu/events", headers=headers, content=_xml(EVENTS).encode())
    assert accepted.status_code == 202
    assert accepted.json()["last_batch_id"] == "xml-1"
    assert accepted.json()["last_event_count"] == 2
    again = client.post("/api/v1/smvu/events", headers=headers, content=_xml(EVENTS, "xml-2"))
    assert again.status_code == 202 and again.json()["last_event_count"] == 0

    with SessionLocal() as session:
        publish_pending(session, get_settings())
    records = [
        json.loads(line)
        for path in tmp_path.glob("*.jsonl")
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    assert [(item["event_id"], item["value"], item["alarm"]) for item in records] == [
        ("x1", "Неисправен", True),
        ("x2", "Норма", False),
    ]
    assert records[1]["ts"] == "2026-07-01T09:05:00"
    audit = client.get("/api/v1/audit", headers=auth_users["admin"]).json()
    assert any(row["action"] == "smvu.ingest" and row["resource_id"] == "xml-1" for row in audit)


def test_xml_batch_without_events_updates_freshness(client: TestClient) -> None:
    body = '<batch id="feed-1" event_count="42" last_event_at="2026-09-29T12:00:00Z"/>'
    response = client.post("/api/v1/smvu/events", headers=XML, content=body)
    assert response.status_code == 202
    assert response.json()["last_event_count"] == 42


def test_xml_batch_uses_json_validation(client: TestClient) -> None:
    cases = [
        _xml(EVENTS, batch_id="bad id"),
        _xml(EVENTS, count=2_000_000),
        _xml('<event event_id="x1" ts="2026-07-01T09:00:00">Норма</event>'),
        _xml('<event event_id="x1" channel_id="1" ts="вчера">Норма</event>'),
        _xml('<event event_id="x1" channel_id="1" ts="2026-07-01T09:00" alarm="maybe">1</event>'),
        _xml(f'<event event_id="x1" channel_id="1" ts="2026-07-01T09:00">{"x" * 121}</event>'),
    ]
    for body in cases:
        response = client.post("/api/v1/smvu/events", headers=XML, content=body)
        assert response.status_code == 422, body
        assert response.json()["detail"][0]["loc"][0] == "body"


def test_xml_rejects_dtd_entities_and_foreign_documents(client: TestClient) -> None:
    bomb = (
        '<?xml version="1.0"?><!DOCTYPE batch [<!ENTITY a "aaaaaaaaaa">'
        '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">]>'
        '<batch id="b" event_count="1"><event event_id="1" channel_id="1" '
        'ts="2026-07-01T09:00:00">&b;</event></batch>'
    )
    external = (
        '<?xml version="1.0"?><!DOCTYPE batch [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        '<batch id="b" event_count="0">&x;</batch>'
    )
    cases = [
        bomb,
        external,
        "<batch id='b' event_count='1'><event>",
        '<feed id="b" event_count="0"/>',
        '<batch id="b" event_count="1"><item/></batch>',
        '{"batch_id": "b", "event_count": 0}',
    ]
    for body in cases:
        response = client.post("/api/v1/smvu/events", headers=XML, content=body)
        assert response.status_code == 422, body
    assert client.get("/api/v1/smvu/status").json()["configured"] is False


def test_openapi_documents_xml_body(client: TestClient) -> None:
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/smvu/events"]["post"]
    content = operation["requestBody"]["content"]
    assert content["application/json"]["schema"]["$ref"].endswith("/SmvuBatchIn")
    assert "<batch" in content["application/xml"]["example"]
