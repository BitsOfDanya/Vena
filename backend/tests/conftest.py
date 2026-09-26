import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

os.environ.setdefault("VENA_SEED_DEMO", "false")
os.environ.setdefault("VENA_DIGEST_ENABLED", "false")
os.environ.setdefault("VENA_INGEST_ON_STARTUP", "false")
os.environ.setdefault(
    "VENA_DATABASE_URL",
    "postgresql+psycopg://vena:vena@localhost:5432/vena_test",
)


def _ensure_database(url: str) -> None:
    """Create the target database if it does not exist yet."""
    sa_url = make_url(url)
    if not sa_url.drivername.startswith("postgresql"):
        raise RuntimeError("VENA_DATABASE_URL must use PostgreSQL (postgresql+psycopg://...)")
    db_name = sa_url.database
    if not db_name:
        raise RuntimeError("VENA_DATABASE_URL must include a database name")
    admin_url = sa_url.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": db_name},
            ).scalar()
            if not exists:
                connection.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin.dispose()


_ensure_database(os.environ["VENA_DATABASE_URL"])

from fastapi.testclient import TestClient  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client() -> Iterator[TestClient]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client
