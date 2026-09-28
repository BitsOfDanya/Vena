# Сборка и установка

## Требования

| Компонент | Версия |
|---|---|
| ОС сервера | Linux (контейнеры), разработка — Linux/macOS |
| Docker / Docker Compose | 24+ / v2 |
| PostgreSQL | 12+ (в compose — 16) |
| Python | 3.12 (backend, ml) |
| Node.js / pnpm | 22 / 10.9 (frontend) |
| Браузер | актуальные Google Chrome, Яндекс.Браузер |

## Запуск в Docker

```bash
docker compose up -d --build
```

| Сервис | Адрес |
|---|---|
| Интерфейс | http://localhost:3100 |
| API и OpenAPI | http://localhost:8100/docs |
| PostgreSQL | 127.0.0.1:5432 (`VENA_DB_PORT` меняет порт на хосте) |

Бэкенд при старте ждёт базу, применяет миграции (`alembic upgrade head`) и читает снимок прогнозов из `ml/results/predictions/snapshot.json`. Каталоги `ml/results`, `ml/configs`, `ml/artifacts` монтируются только на чтение.

Вход в интерфейс — по API-ключу. Ключи и роли задаются `VENA_API_KEYS_JSON`, например `{"<ключ>":"admin"}`. Для публичного стенда задайте собственные ключи: значения по умолчанию в `compose.yaml` предназначены только для локального запуска.

## Снимок прогнозов

Снимок не хранится в репозитории: он строится из журнала СМВУ, который не распространяется.

С журналом (`ml/dataset/ext-journal-*.csv`, `ml/dataset/справочник_каналов_датчиков.csv`):

```bash
cd ml
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python score_snapshot.py
```

Без журнала — синтетические каналы стенда, оценённые теми же замороженными моделями:

```bash
python score_snapshot.py --demo
```

После появления нового снимка бэкенд подхватывает его автоматически; принудительная обработка — `POST /api/v1/predictions/refresh` с ролью `dispatcher`.

## Переобучение моделей

```bash
cd ml
python run_production_refresh.py
```

Скрипт заново извлекает события, замораживает модели насосов, вентиляторов, дыма и питания, сравнивает смесь моделей насоса 72 ч с базовой и пишет новый снимок. Отдельные шаги: `run_final_freeze.py <device> <horizon> <model>`, `run_pump_blend_freeze.py`, `run_power_freeze.py`, `score_snapshot.py`.

## Локальная разработка

База:

```bash
docker compose up -d db
```

Backend:

```bash
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run fastapi dev
```

Frontend:

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

## Переменные окружения

| Переменная | Назначение |
|---|---|
| `VENA_DATABASE_URL` | строка подключения PostgreSQL (`postgresql+psycopg://…`) |
| `VENA_ML_DIR` | каталог ML-компонента |
| `VENA_AUTH_ENABLED`, `VENA_API_KEYS_JSON` | включение RBAC и ключи с ролями `admin` / `dispatcher` / `viewer` |
| `VENA_PREDICTION_STALE_SECONDS` | возраст снимка, после которого выводится уведомление об устаревании |
| `VENA_SEED_DEMO`, `VENA_DIGEST_ENABLED`, `VENA_TIMEZONE`, `VENA_PUBLIC_URL` | демо-данные, утренний дайджест, часовой пояс, публичный адрес |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` | почтовые уведомления; без `SMTP_HOST` канал email отключён |
| `NEXT_PUBLIC_API_URL` | адрес API для интерфейса (задаётся при сборке) |
| `NEXT_PUBLIC_VENA_WORKFLOW_MODE` | `api` — работы и уведомления в PostgreSQL; `demo` — в браузере |
| `NEXT_PUBLIC_VENA_DATA_MODE` | источник телеметрии для визуализаций: `demo` |

## Резервное копирование

```bash
backend/scripts/backup-postgres.sh
```

Скрипт пишет `backups/vena-<время UTC>.sql.gz` и хранит 14 последних копий. Каталог и контейнер переопределяются `VENA_BACKUP_DIR` и `VENA_DB_CONTAINER`. Для автоматического копирования скрипт ставится в cron хоста.

Восстановление:

```bash
gunzip -c backups/vena-<время>.sql.gz | docker exec -i vena-db-1 psql -U vena -d vena
```

## Проверки

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
```

Тесты backend требуют запущенный PostgreSQL; база `vena_test` создаётся автоматически.
