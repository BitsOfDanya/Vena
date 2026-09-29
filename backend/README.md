# VENA backend

REST API сервиса: FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, APScheduler. Все маршруты — под `/api/v1`, OpenAPI — `/docs`.

```bash
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed_users
uv run fastapi dev
```

## Структура

```
app/api/routes/   HTTP-слой: 15 роутеров, проверка ролей
app/domain/       логика: приём снимка, инциденты, работы, журнал, уведомления,
                  очередь писем, импорт CSV/XLSX, реестр, поток СМВУ, отчёты, аудит
app/schemas/      Pydantic-контракты запросов и ответов
app/db/           модели SQLAlchemy, сессия, сиды пользователей и демо-данных
app/core/         настройки, JWT и RBAC, LDAP
migrations/       Alembic, линейная цепочка миграций
scripts/          entrypoint контейнера, init-db.sql, локальный бэкап
tests/            pytest на PostgreSQL
```

## Фоновые задания

| Задание | Период | Что делает |
|---|---|---|
| `prediction_refresh` | 30 с | новый снимок ML → история оценок, инциденты, уведомления, черновики работ |
| `email_delivery` | 10 с | отправка писем из очереди `delivery_log` с повторами |
| `import_publications` | 10 с | публикация принятых загрузок и пакетов потока для ML-контейнера |
| `equipment_sync` | 15 мин (настраивается) | синхронизация реестра с учётной системой, если включена |
| `morning_brief` | ежедневно | утренняя сводка |

Модели в процесс API не загружаются: backend читает готовый снимок `ml/results/predictions/snapshot.json` и результаты из `VENA_ML_DIR`.

## Проверки

```bash
uv run ruff check . && uv run mypy app && uv run pytest
```

Тестам нужен PostgreSQL. По умолчанию используется `postgresql+psycopg://vena:vena@localhost:5432/vena_test`, база создаётся автоматически.

Переменные окружения, роли и интеграции описаны в [docs/installation.md](../docs/installation.md), [docs/authentication.md](../docs/authentication.md) и [docs/data-integrations.md](../docs/data-integrations.md).
