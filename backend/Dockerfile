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
    "psycopg[binary]>=3.2" \
    "PyJWT>=2.10" \
    "argon2-cffi>=25.1" \
    "openpyxl>=3.1"

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
