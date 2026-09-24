# Vena

Платформа предиктивного обслуживания инженерных систем (кейс №8, АО «Москоллектор», ЛЦТ 2026): ML-модели по журналу событий датчиков, HTTP API и веб-интерфейс.

## Repository structure

```
backend/    FastAPI: health, ML-эндпоинты (модели, направления, таблицы результатов)
frontend/   Next.js (App Router, TypeScript, Tailwind, shadcn/ui, Feature-Sliced Design)
ml/         ML-компонент: pipeline, модели, конфиги, тесты, результаты экспериментов
```

Данные журнала событий не хранятся в репозитории (проприетарные): каталог `ml/dataset/` создаётся локально.

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

```bash
docker compose up -d --build
```

| Сервис | Порт | Данные |
|---|---|---|
| frontend (Next.js) | `http://localhost:3100` | — |
| backend (FastAPI) | `http://localhost:8100/docs` | том `vena-data` (SQLite) |

Каталоги `ml/results`, `ml/configs` и `ml/artifacts` монтируются в контейнер API только на чтение (`VENA_ML_DIR=/srv/ml`); датасет событий (15 ГБ) в образ не попадает и не монтируется.

### Environment

Бэкенд читает переменные с префиксом `VENA_` (см. `backend/.env.example`): `VENA_DATABASE_URL`, `VENA_PUBLIC_URL`, `VENA_TIMEZONE`, `VENA_SEED_DEMO`, `VENA_DIGEST_ENABLED`. Почта настраивается только через окружение: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` — значения не хранятся ни в базе, ни во фронтенде, ни в репозитории. Пока `SMTP_HOST`/`SMTP_FROM` пусты, канал Email отображается как `Not configured`, а `POST /api/v1/notifications/test` возвращает `409`.

Фронтенд собирается с `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_VENA_DATA_MODE` (источник телеметрии: `demo` — детерминированный снимок) и `NEXT_PUBLIC_VENA_WORKFLOW_MODE` (`api` — уведомления, работы и настройки идут в бэкенд; `demo` — локальное хранилище браузера).

### Predictions

Модели не переобучаются и не запускаются внутри API. Скоринг выполняется офлайн:

```bash
cd ml && python score_snapshot.py
```

Скрипт загружает замороженные артефакты (`ml/artifacts/models/*`), считает признаки по кэшу событий и записывает снимок `ml/results/predictions/snapshot.json`. Бэкенд читает этот файл только на чтение, отображает `risk_level` по порогам из `ml/configs/models/*.json` и никогда не выдаёт `probability`, пока `calibrated=false` (сейчас у всех моделей `false`, поэтому `score_type=risk_score`).

Уровни: `critical` / `attention` (`high` в конфиге) / `observe` (`medium`) / `normal`. Порог устаревания снимка — `VENA_PREDICTION_STALE_SECONDS`; при превышении появляется системное уведомление, но API остаётся здоровым. Если снимка нет, `/predictions` возвращает `503`, а интерфейс в API-режиме показывает «Predictions unavailable» и не подставляет демо-значения.

### What is real and what is demo

| Блок | Состояние |
|---|---|
| Прогнозы, уровни риска, ситуации, автоуведомления | считаются бэкендом по снимку реальных моделей |
| Уведомления, подтверждения, работы, история, результаты, настройки уведомлений | хранятся в БД бэкенда |
| Связка прогноз → работа → результат (`/ml/feedback`) | хранится в БД |
| System notices | вычисляются бэкендом по доступности ML-каталогов и свежести снимка |
| Телеметрия событий, активность, Network/Timeline | детерминированный демо-снимок во фронтенде (помечен «demo telemetry») |
| Корреляционные паттерны | только в demo-режиме; бэкенд-детектора нет |
| Email, Morning brief | код и планировщик есть, отправка включается только настроенным SMTP |
| Аутентификация, карта, аналитический Dashboard | не реализованы |

## Local development

Backend (порт 8000; если занят — укажите другой):

```bash
cd backend
cp .env.example .env
uv sync
uv run fastapi dev
```

Без `uv`:

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install "fastapi[standard-no-fastapi-cloud-cli]" pydantic-settings httpx mypy pytest ruff
.venv/bin/uvicorn app.main:app --port 8000
```

Frontend (во втором терминале):

```bash
cd frontend
cp .env.example .env.local
pnpm install
pnpm dev
```

Открыть `http://localhost:3000`. Документация API: `http://localhost:8000/docs`, каталог компонентов: `http://localhost:3000/design-system`.

## Web interface

Интерфейс — временная схема инженерной инфраструктуры: `Network → Risk → Reason → Action → Result`, прошлое, настоящее и прогноз на одной оси. Тема по умолчанию — Mineral Light (светлое инженерное полотно, графитовая шапка).

| Раздел | Назначение |
|---|---|
| `/pulse` | живая активность инфраструктуры: состояние системы, события по типам оборудования, коррелированные паттерны, лента событий |
| `/network` | схема состояния инфраструктуры, инспектор объекта, диагностика риска по объекту |
| `/timeline` | история и прогноз вокруг текущего момента (PAST · NOW · FUTURE), сравнение до 5 объектов |
| `/actions` | план обслуживания на 24/48/72 часа, фиксация результата работ |
| `/dashboard` | отдельный аналитический модуль |

Режим Replay воспроизводит исторический эпизод; события открываются только после текущего времени воспроизведения. Командная палитра — `Ctrl/Cmd + K`.

Режим карты требует реальных пространственных данных (GeoJSON/WKT) и намеренно не имитируется: координаты и топология не выдумываются, схема группирует объекты только по имеющимся данным. Оценка риска показывается как `risk score N/100` и не выдаётся за вероятность, пока модель не откалибрована.

Модуль Dashboard зарезервирован под отдельную реализацию. Pulse, Network, Timeline и Actions не зависят от его компонентов.

Источник данных задаётся `NEXT_PUBLIC_VENA_DATA_MODE` (`demo` по умолчанию) и `NEXT_PUBLIC_VENA_ENVIRONMENT`; демонстрационный набор детерминирован и расположен в `frontend/src/entities/infrastructure/fixtures/demo.ts`, обращение к нему идёт через сервисные функции, которые заменяются REST-клиентом.

## API

| Метод и путь | Назначение |
|---|---|
| `GET /api/v1/health` | состояние сервиса |
| `GET /api/v1/ml/directions` | направления, статусы и метрики |
| `GET /api/v1/ml/models` | замороженные модели (тип, число признаков, период обучения) |
| `GET /api/v1/ml/results` | список таблиц результатов по группам |
| `GET /api/v1/ml/results/{group}/{name}?limit=N` | строки таблицы результатов (`tables`, `formal_70_50`, `new_directions`) |
| `GET/POST /api/v1/notifications`, `PATCH /api/v1/notifications/{id}` | уведомления и переходы `new → acknowledged → resolved` |
| `POST /api/v1/notifications/test` | тестовое письмо (409, если SMTP не настроен) |
| `GET/POST /api/v1/actions`, `PATCH /api/v1/actions/{id}` | работы обслуживания |
| `POST /api/v1/actions/{id}/{approve,dismiss,assign,start,wait,cancel,result}` | жизненный цикл и результат работы |
| `GET /api/v1/situations` | ситуации, собранные из уведомлений и открытых работ |
| `GET /api/v1/system/notices`, `GET /api/v1/system/components` | системные уведомления и состояние компонентов |
| `GET/PUT /api/v1/settings/notifications` | каналы, правила, получатели, дайджест |
| `GET /api/v1/predictions` | прогнозы из снимка ML (фильтры, сортировки `risk_desc`/`delta_desc`/`latest`) |
| `GET /api/v1/predictions/snapshot` | идентификатор снимка, время расчёта, возраст, признак устаревания |
| `POST /api/v1/predictions/refresh` | приём нового снимка: дедупликация, история, правила уведомлений |
| `GET /api/v1/assets/{id}/prediction`, `GET /api/v1/assets/{id}/predictions` | текущий прогноз и история по объекту |
| `GET /api/v1/ml/feedback` | связка прогноз → работа → результат для будущего дообучения |
| `GET /api/v1/integrations/email/status` | состояние почтового канала без секретов |

Путь к каталогу ML задаётся `VENA_ML_DIR` (по умолчанию `ml/` в корне репозитория).

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
```

Миграции базы: `cd backend && uv run alembic upgrade head` (в контейнере выполняются при старте).
