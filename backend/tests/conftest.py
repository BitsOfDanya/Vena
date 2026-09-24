import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

os.environ.setdefault("VENA_SEED_DEMO", "false")
os.environ.setdefault("VENA_DIGEST_ENABLED", "false")
os.environ.setdefault("VENA_INGEST_ON_STARTUP", "false")
_db_path = Path(tempfile.gettempdir()) / "vena-tests.db"
_db_path.unlink(missing_ok=True)
os.environ["VENA_DATABASE_URL"] = f"sqlite:///{_db_path}"

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
