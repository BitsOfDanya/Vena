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

## API

| Метод и путь | Назначение |
|---|---|
| `GET /api/v1/health` | состояние сервиса |
| `GET /api/v1/ml/directions` | направления, статусы и метрики |
| `GET /api/v1/ml/models` | замороженные модели (тип, число признаков, период обучения) |
| `GET /api/v1/ml/results` | список таблиц результатов по группам |
| `GET /api/v1/ml/results/{group}/{name}?limit=N` | строки таблицы результатов (`tables`, `formal_70_50`, `new_directions`) |

Путь к каталогу ML задаётся `VENA_ML_DIR` (по умолчанию `ml/` в корне репозитория).

## Checks

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm build
cd ml && python -m pytest
```
