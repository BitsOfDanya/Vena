# Vena backend

FastAPI service for Vena.

```bash
uv sync
uv run fastapi dev
```

The API is served at `http://127.0.0.1:8000`, with OpenAPI docs at `/docs`.

ML endpoints under `/api/v1/ml` read frozen model configs and result tables from the `ml/` directory (override with `VENA_ML_DIR`). They are read-only; models are not loaded into the API process.

```bash
uv run ruff check . && uv run mypy app && uv run pytest
```
