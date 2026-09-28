FROM ghcr.io/astral-sh/uv:0.11.19 AS uv
FROM python:3.12-slim AS build
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /srv/app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project --no-editable

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/srv/app/.venv/bin:$PATH VENA_ML_DIR=/srv/ml
WORKDIR /srv/app
RUN useradd --uid 10001 --create-home app
COPY --from=build /srv/app/.venv ./.venv
COPY --chown=app:app backend/app ./app
COPY --chown=app:app backend/migrations ./migrations
COPY --chown=app:app backend/alembic.ini ./
COPY --chmod=755 backend/scripts/entrypoint.sh ./scripts/entrypoint.sh
COPY --chown=app:app ml/configs /srv/ml/configs
COPY --chown=app:app ml/artifacts /srv/ml/artifacts
COPY --chown=app:app ml/results /srv/ml/results
RUN mkdir -p /srv/ml/inbox && chown app:app /srv/ml/inbox
USER 10001
EXPOSE 8000
CMD ["./scripts/entrypoint.sh"]
