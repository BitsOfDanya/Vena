#!/bin/sh
set -eu

python - <<'PY'
import os, socket, time, urllib.parse

url = os.environ["VENA_DATABASE_URL"]
if not url.startswith("postgresql"):
    raise SystemExit("VENA_DATABASE_URL must be a PostgreSQL URL (postgresql+psycopg://...)")

parsed = urllib.parse.urlparse(url.replace("postgresql+psycopg", "postgresql", 1))
host = parsed.hostname or "localhost"
port = parsed.port or 5432
deadline = time.time() + 60
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit(f"database not reachable at {host}:{port}")
PY

alembic upgrade head
if [ "${VENA_SEED_USERS:-false}" = "true" ]; then
    python -m app.db.seed_users
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
