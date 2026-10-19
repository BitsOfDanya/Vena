import asyncio

from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy import create_engine

from app.api.routes import health
from app.main import app


async def get_health() -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/health")


def test_health_check() -> None:
    response = asyncio.run(get_health())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Vena API",
        "version": "0.1.0",
        "database": "ok",
    }


def test_health_check_reports_unavailable_database(monkeypatch) -> None:
    unreachable = create_engine("postgresql+psycopg://vena:vena@127.0.0.1:1/vena")
    monkeypatch.setattr(health, "engine", unreachable)

    response = asyncio.run(get_health())

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["database"] == "unavailable"
