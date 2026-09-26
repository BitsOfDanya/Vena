# Vena

Платформа предиктивного обслуживания инженерных систем (кейс №8, АО «Москоллектор», ЛЦТ 2026): ML-модели по журналу событий датчиков, HTTP API и веб-интерфейс.

## Repository structure

```
backend/    FastAPI + PostgreSQL: predictions, actions, notifications, spatial, auth/audit
frontend/   Next.js (App Router, TypeScript, Tailwind, shadcn/ui, Feature-Sliced Design)
ml/         ML-компонент: pipeline, модели, конфиги, тесты, результаты экспериментов
```

Данные журнала событий не хранятся в репозитории (проприетарные): каталог `ml/dataset/` создаётся локально. SQLite не используется — только PostgreSQL 12+.

## ML directions

| Направление | Статус |
|---|---|
| Sensor Health, Equipment Health (насос, вентилятор, дым) | замороженные модели в `ml/artifacts/models` |
| Power Health (питание фазы, «Обесточен» за 24ч) | кандидат в production |
| Alarm Intelligence (подтверждение тревог) | shadow-режим |
| Incident Risk Proxies (Fire/Smoke Risk Index, Hydraulic Load Anomaly) | только proxy-индексы |
| Maintenance Priority | решающее правило, не обучаемый target |

Формальная цель Precision ≥ 0.70 и Recall ≥ 0.50 для отказов насосов и вентиляторов **не достигнута**; для Power Health на rolling-валидации достигается. Подробности — в [ml/README.md](ml/README.md), сводная таблица направлений — `ml/results/directions.json`.

## Run with Docker

Фронтенд-образ упаковывает уже собранный `.next` (офлайн-friendly). Перед первым `compose up --build` или после изменений UI:

```bash
cd frontend && pnpm install && pnpm build
cd .. && docker compose up -d --build
```

| Сервис | Порт | Данные |
|---|---|---|
| frontend (Next.js) | `http://localhost:3100` | — |
| backend (FastAPI) | `http://localhost:8100/docs` | PostgreSQL (`db`) |
| db (PostgreSQL 16) | `localhost:5432` | том `vena-postgres` |

Каталоги `ml/results`, `ml/configs` и `ml/artifacts` монтируются в контейнер API только на чтение (`VENA_ML_DIR=/srv/ml`); датасет событий в образ не попадает. При старте backend ждёт Postgres и выполняет `alembic upgrade head`.

### Environment

Бэкенд читает переменные с префиксом `VENA_` (см. `backend/.env.example`):

| Переменная | Назначение |
|---|---|
| `VENA_DATABASE_URL` | PostgreSQL 12+ (`postgresql+psycopg://…`); в Docker — `vena:vena@db:5432/vena` |
| `VENA_AUTH_ENABLED` / `VENA_API_KEYS_JSON` | API-key RBAC (`admin` / `dispatcher` / `viewer`); без auth стенд работает с полным доступом |
| `VENA_PUBLIC_URL`, `VENA_TIMEZONE`, `VENA_SEED_DEMO`, `VENA_DIGEST_ENABLED` | публичный URL, TZ, демо-seed, morning digest |
| `VENA_PREDICTION_STALE_SECONDS` | порог устаревания ML-снимка |
| `SMTP_*` | почта только из окружения; секреты не в БД и не в репозитории |

Пока `SMTP_HOST`/`SMTP_FROM` пусты, канал Email — `Not configured`, `POST /api/v1/notifications/test` → `409`.

Фронтенд: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_VENA_DATA_MODE` (`demo` — детерминированная телеметрия), `NEXT_PUBLIC_VENA_WORKFLOW_MODE` (`api` — уведомления/работы/настройки в бэкенд; `demo` — localStorage). API-ключ UI хранится в `localStorage` и уходит как `X-API-Key` (`Settings → Security`).

### Predictions

Модели не переобучаются и не запускаются внутри API. Скоринг офлайн:

```bash
cd ml && python score_snapshot.py
# без журнала СМВУ (стенд):
cd ml && python score_snapshot.py --demo
```

Скрипт пишет `ml/results/predictions/snapshot.json`. Бэкенд читает снимок только на чтение; при `calibrated=false` наружу идёт `score_type=risk_score`, не probability.

В API-режиме уровни риска на Pulse, Network, Timeline и Actions берутся из snapshot (шкала UI 0–100); телеметрия событий на Pulse пока demo.

Уровни: `critical` / `attention` (`high`) / `observe` (`medium`) / `normal`. Устаревший снимок → системное уведомление, API остаётся healthy. Нет снимка → `/predictions` `503`, UI показывает «Predictions unavailable».

Ingest критических прогнозов создаёт уведомления и черновики работ (`status=suggested`, `source=vena_forecast`).

### Spatial / SMVU / backup

- **Карта:** режим Map на `/network` — GeoJSON-слой + risk overlay. Стенд сидирует `demo_spatial`; прод-данные — `PUT /api/v1/spatial` (FeatureCollection) или `PUT /api/v1/spatial/wkt` (POINT).
- **СМВУ:** `POST /api/v1/smvu/events` фиксирует свежесть батча (цель ≤5 мин); полный журнал событий и live-телеметрия в API — следующий этап.
- **Backup:** `backend/scripts/backup-postgres.sh` → `backups/vena-*.sql.gz` (том/каталог в `.gitignore`).

### What is real and what is demo

| Блок | Состояние |
|---|---|
| Прогнозы, уровни риска, ситуации, автоуведомления и suggested-работы | снимок реальных моделей → API |
| Network / Timeline / Actions risk (api-режим) | overlay из `/predictions` на демо-активах |
| Уведомления, работы, история, результаты, настройки | PostgreSQL |
| Связка прогноз → работа → результат (`/ml/feedback`) | PostgreSQL |
| System notices | ML-каталоги + свежесть снимка |
| Телеметрия событий, активность, topology | demo fixtures во фронтенде |
| Корреляционные паттерны | только demo на фронте |
| Email, Morning brief | код есть; нужна настройка SMTP |
| Аутентификация | API-key RBAC + UI Security/Audit; LDAP/AD — следующий шаг |
| Карта | Map mode; стенд `demo_spatial`, импорт GeoJSON/WKT |
| SMVU | хук свежести батчей; streaming journal — нет |
| Backup Postgres | скрипт есть; нужен регламент cron/restore |
| TLS / reverse proxy | не в compose (вынести на ingress) |
| Аналитический Dashboard | заглушка, отдельная реализация |

## Local development

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

Без `uv`:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install "fastapi[standard-no-fastapi-cloud-cli]" pydantic-settings httpx mypy pytest ruff "psycopg[binary]" alembic sqlalchemy apscheduler
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend:

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

Открыть `http://localhost:3000`. API docs: `http://localhost:8000/docs`, design system: `http://localhost:3000/design-system`.

## Web interface

Контур диспетчера: `Network → Risk → Reason → Action → Result`. Тема — Mineral Light.

| Раздел | Назначение |
|---|---|
| `/pulse` | активность, паттерны, лента событий |
| `/network` | схема / таблица активов / **Map**, инспектор, диагностика |
| `/timeline` | PAST · NOW · FUTURE, сравнение до 5 объектов |
| `/actions` | план ТО 24/48/72ч, результат работ |
| `/settings` | overview, notifications, integrations, **security**, **audit** |
| `/dashboard` | заглушка аналитического модуля |

Replay — `Ctrl/Cmd + K` (command palette). Риск на UI — `risk score N/100`, не вероятность, пока модель не откалибрована.

## API

| Метод и путь | Назначение |
|---|---|
| `GET /api/v1/health` | состояние сервиса |
| `GET /api/v1/auth/me` | текущий principal / роль |
| `GET /api/v1/audit` | журнал RBAC-действий (admin) |
| `GET /api/v1/ml/directions` | направления, статусы и метрики |
| `GET /api/v1/ml/models` | замороженные модели |
| `GET /api/v1/ml/results`, `…/{group}/{name}` | таблицы результатов |
| `GET/POST /api/v1/notifications`, `PATCH …/{id}` | уведомления |
| `POST /api/v1/notifications/test` | тестовое письмо |
| `GET/POST /api/v1/actions`, lifecycle `…/{approve,dismiss,…,result}` | работы ТО |
| `GET /api/v1/situations` | ситуации из уведомлений и открытых работ |
| `GET /api/v1/system/notices`, `…/components` | системные notices |
| `GET/PUT /api/v1/settings/notifications` | каналы, правила, дайджест |
| `GET /api/v1/predictions`, `…/snapshot`, `POST …/refresh` | прогнозы и ingest снимка |
| `GET /api/v1/assets/{id}/prediction`, `…/predictions` | прогноз по объекту |
| `GET /api/v1/ml/feedback` | связка прогноз → работа → результат |
| `GET/PUT /api/v1/spatial`, `PUT …/wkt`, `POST …/demo` | GeoJSON/WKT карта |
| `GET /api/v1/smvu/status`, `POST …/events` | свежесть потока СМВУ |
| `GET /api/v1/integrations/email/status` | SMTP без секретов |

`VENA_ML_DIR` — путь к каталогу ML (по умолчанию `ml/` в корне репозитория).

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
```

Перед тестами backend: `docker compose up -d db`, затем `cd backend && uv run pytest` (БД `vena_test` создаётся автоматически).
