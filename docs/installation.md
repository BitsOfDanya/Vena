# Сборка и установка

## Требования

| Компонент | Версия |
|---|---|
| ОС сервера | Linux x86-64 (Docker); разработка — Linux или macOS |
| Docker / Docker Compose | 24+ / v2 |
| PostgreSQL | 16 (образ `postgres:16-alpine`) |
| Python | 3.12 (backend, ML) |
| Node.js / pnpm | 22 / 10.9 (frontend) |
| Браузер | актуальные Google Chrome, Яндекс.Браузер |
| Память стенда | ML-контейнер ограничен 3 CPU и 5 ГБ RAM (`infra/compose.yaml`) |

## Production-стенд

Стенд: https://5bit.online. Подготовка сервера, HTTPS, автодеплой из `main`, откат, резервные копии и загрузка журнала описаны в [infra/README.md](../infra/README.md).

## Локальный запуск в Docker

```bash
docker compose up -d --build
```

| Сервис | Адрес |
|---|---|
| Интерфейс | http://localhost:3100 |
| API и OpenAPI | http://localhost:8100/docs |
| PostgreSQL | 127.0.0.1:5432 (порт на хосте меняет `VENA_DB_PORT`) |

При старте backend ждёт базу, применяет миграции (`alembic upgrade head`) и каждые 30 с проверяет снимок прогнозов `ml/results/predictions/snapshot.json`. Каталоги `ml/results`, `ml/configs`, `ml/artifacts` монтируются только на чтение. В локальном compose нет ML-контейнера и Caddy, поэтому снимок строится вручную (раздел ниже).

Пользователи. Аутентификация включена, пустая база пользователей не содержит:

```bash
docker compose exec backend python -m app.db.seed_users
docker compose exec -e VENA_USER_PASSWORD=<пароль> backend \
  python -m app.db.seed_users --username admin --email admin@example.com --role admin
```

Первая команда создаёт `user1`–`user20` с ролью `dispatcher`, вторая — администратора. Подробности в [authentication.md](authentication.md).

## Снимок прогнозов

Снимок не хранится в репозитории: он строится из журнала СМВУ, а журнал не распространяется.

По журналу (`ml/dataset/ext-journal-*.csv`, `ml/dataset/справочник_каналов_датчиков.csv`):

```bash
cd ml
python3 -m venv .venv && . .venv/bin/activate
pip install -r ../infra/docker/ml-requirements.txt
python score_snapshot.py
```

Без журнала те же замороженные модели оценивают синтетические каналы насосов, вентиляторов и дымовых датчиков:

```bash
python score_snapshot.py --demo
```

Новый снимок backend подхватывает сам. Принудительная обработка: `POST /api/v1/predictions/refresh` с ролью `dispatcher`. Для полного исследовательского окружения (PyTorch, numba, XGBoost) используйте `ml/requirements.txt`.

## Переобучение моделей

```bash
cd ml
python run_production_refresh.py
```

Скрипт заново извлекает события и переобучает все модели. Претендент заменяет текущую модель, только если его AP на отложенном периоде выше. Затем модели калибруются, пересчитываются аналитика доступа и сезонности, реестр моделей и снимок. Отдельные шаги: `run_final_freeze.py <device> <horizon> <model>`, `run_pump_blend_freeze.py`, `run_power_freeze.py`, `run_flood_freeze.py`, `run_alarm_freeze.py`, `run_calibration.py`, `run_refit_study.py --promote`, `run_access_analysis.py`, `run_seasonality.py`, `score_snapshot.py`. Протокол — [ml/README.md](../ml/README.md).

## Локальная разработка без Docker

```bash
docker compose up -d db

cd backend
cp .env.example .env          # задайте VENA_JWT_SECRET (openssl rand -hex 32)
uv sync
uv run alembic upgrade head
uv run python -m app.db.seed_users
uv run fastapi dev            # http://127.0.0.1:8000

cd ../frontend
cp .env.example .env.local    # NEXT_PUBLIC_VENA_WORKFLOW_MODE=api для работы с backend
pnpm install
pnpm dev                      # http://localhost:3000
```

## Переменные окружения

Backend читает переменные с префиксом `VENA_` из окружения и `backend/.env`. Полный список — `backend/app/core/config.py`, пример — `backend/.env.example`, для стенда — `infra/.env.example`.

| Переменная | Назначение |
|---|---|
| `VENA_DATABASE_URL` | строка подключения PostgreSQL (`postgresql+psycopg://…`) |
| `VENA_ENVIRONMENT` | `local`, `test`, `staging`, `production` |
| `VENA_PUBLIC_URL`, `VENA_CORS_ORIGINS` | публичный адрес (ссылки в письмах, проверка Origin, флаг `Secure` у cookie) и разрешённые источники |
| `VENA_TIMEZONE` | часовой пояс отчётов и сводки, по умолчанию `Europe/Moscow` |
| `VENA_AUTH_ENABLED`, `VENA_JWT_SECRET`, `VENA_JWT_TTL_MINUTES` | вход и JWT; секрет не короче 32 байт. В коде по умолчанию вход выключен, в compose и примерах включён |
| `VENA_AUTH_LOGIN_LIMIT`, `VENA_AUTH_LOGIN_WINDOW_SECONDS` | ограничение попыток входа |
| `VENA_LDAP_*` | LDAP/AD, см. [data-integrations.md](data-integrations.md#ldap--active-directory-тз-11) |
| `VENA_SEED_USERS` | создать `user1`–`user20` при старте контейнера |
| `VENA_SEED_DEMO` | демонстрационные работы, уведомления и геослой карты |
| `VENA_ML_DIR` | каталог ML (снимок, реестр моделей, результаты) |
| `VENA_DATASET_DIR` | каталог принятых загрузок CSV/XLSX; без него импорт через интерфейс выключен |
| `VENA_INBOX_DIR` | очередь пакетов потока СМВУ для ML-контейнера |
| `VENA_PREDICTION_REFRESH_SECONDS` | период проверки нового снимка, 30 с |
| `VENA_PREDICTION_STALE_SECONDS` | возраст снимка, после которого показывается предупреждение |
| `VENA_PREDICTION_CRITICAL_LIMIT`, `VENA_PREDICTION_COOLDOWN_MINUTES` | лимит уведомлений на сценарий и пауза повторов |
| `VENA_EQUIPMENT_SYNC_*` | синхронизация реестра с учётной системой |
| `VENA_UPLOAD_MAX_BYTES`, `VENA_UPLOAD_MAX_ROWS` | лимиты загрузки файла |
| `VENA_DIGEST_ENABLED` | утренняя сводка |
| `SMTP_*` | почта, см. [email-notifications.md](email-notifications.md) |
| `VENA_ML_MODE` | ML-контейнер: `auto`, `journal`, `demo` |
| `VENA_ML_REFRESH_SECONDS`, `VENA_STREAM_POLL_SECONDS` | период демо-пересчёта и опроса очереди потока |
| `NEXT_PUBLIC_API_URL` | адрес API для интерфейса, задаётся при сборке |
| `NEXT_PUBLIC_VENA_WORKFLOW_MODE` | `api` — данные и работы из backend; `demo` — автономный режим интерфейса без API |

## Резервное копирование

На стенде копии делает `infra/scripts/backup.sh` по таймеру systemd `vena-backup.timer`, ежедневно в 03:00 UTC. Сохраняются дамп PostgreSQL, каталог загрузок и очередь потока, хранятся 14 дней. Восстановление и проверка копии во временной базе (`infra/scripts/verify-backup.sh`) описаны в [infra/README.md](../infra/README.md#резервные-копии).

Для локальной базы:

```bash
backend/scripts/backup-postgres.sh
gunzip -c backups/vena-<время>.sql.gz | docker exec -i vena-db-1 psql -U vena -d vena
```

## Проверки

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
```

Тестам backend нужен запущенный PostgreSQL; база `vena_test` создаётся автоматически (`VENA_DATABASE_URL` переопределяет адрес).
