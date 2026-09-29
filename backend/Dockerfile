FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VENA_ML_DIR=/srv/ml

WORKDIR /srv/app

RUN pip install --no-cache-dir \
    "fastapi[standard-no-fastapi-cloud-cli]>=0.141.1" \
    "pydantic-settings>=2.15.0" \
    "sqlalchemy>=2.0.54" \
    "alembic>=1.20.0" \
    "apscheduler>=3.11.0" \
    "email-validator>=2.2.0" \
    "psycopg[binary]>=3.2.0" \
    "openpyxl>=3.1" \
    "pyjwt>=2.10,<3" \
    "pwdlib[argon2]>=0.3,<1"

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
COPY scripts/entrypoint.sh ./scripts/entrypoint.sh
RUN chmod +x ./scripts/entrypoint.sh

EXPOSE 8000

CMD ["./scripts/entrypoint.sh"]
