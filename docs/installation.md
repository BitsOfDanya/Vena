# Сборка и установка

## Требования

| Компонент | Версия |
|---|---|
| ОС | Linux x86-64 для стенда; Linux или macOS для разработки |
| Docker / Docker Compose | 24+ / v2 |
| PostgreSQL | 16 (`postgres:16-alpine`) |
| Python / Node.js / pnpm | 3.12 (backend, ML) / 22 / 10.9 (frontend) |
| Браузер | актуальные Google Chrome, Яндекс.Браузер |

## Локальный запуск в Docker

```bash
docker compose up -d --build --wait   # без --wait проверяйте готовность через docker compose ps
```

Первая сборка занимает около 10 минут, повторный запуск — около минуты. Стенд готов, когда все сервисы в `docker compose ps` в состоянии `healthy`. Порядок старта: `db` и `ml` → `backend` → `frontend`.

| Сервис | Адрес на хосте | Проверка готовности |
|---|---|---|
| `frontend` | http://localhost:3100 (`VENA_UI_PORT`) | ответ `/pulse` |
| `backend` | http://localhost:8100/docs — OpenAPI (`VENA_API_PORT`) | `GET /api/v1/health` |
| `db` | 127.0.0.1:5432 (`VENA_DB_PORT`) | `pg_isready` |
| `ml` | — | файл `heartbeat` в томе снимка не старше 2 ч; первые 5 мин сбои не учитываются |
| `helpdesk` | http://127.0.0.1:8090 (`VENA_HELPDESK_PORT`) | `GET /health`; [эмулятор](data-integrations.md#эмуляторы-внешних-систем) |
| `ldap` | только в сети compose, профиль `ldap` | `ldapsearch`; [тестовый каталог](authentication.md#тестовый-каталог-ldap) |

Вход: `user1` / `0987654321` — администратор, `user2`–`user20` с тем же паролем — диспетчеры. Учётные записи создаются при первом старте backend (`VENA_SEED_USERS=true`, `VENA_SEED_ADMIN=user1`, пароль — `VENA_USER_PASSWORD`). При повторном старте существующие записи не меняются. Роли и области видимости описаны в [authentication.md](authentication.md).

Адрес API вшивается в интерфейс при сборке, поэтому после смены `VENA_API_PORT` нужен `--build`. Остановка — `docker compose down`, с удалением базы, снимка и очередей — `docker compose down -v`.

### Журнал СМВУ и демонстрационный снимок

Журнал в репозиторий не входит. Перед запуском положите в `ml/dataset` (другой каталог задаёт `VENA_DATASET_DIR`) журнал `ext-journal-*.csv` (один или несколько файлов) и справочник `справочник_каналов_датчиков.csv`. ML-контейнер (`VENA_ML_MODE=auto`) проверяет каталог каждые 5 с. Если есть оба файла, `ml` один раз оценивает журнал целиком (на полном журнале это занимает десятки минут), а затем пересчитывает прогнозы по потоку событий. Если файлов нет, публикуется демонстрационный снимок: те же замороженные модели оценивают синтетические каналы насосов, вентиляторов и дымовых датчиков. API помечает такой снимок `data_source=demo`. Журнал, загруженный через интерфейс (**Настройки → Интеграции**), попадает в тот же каталог, и `ml` переключается на него без перезапуска. Подробнее — в [data-integrations.md](data-integrations.md). Если каталога нет, Docker создаёт его сам (на Linux — от root), поэтому журнал лучше положить до первого запуска. Backend подхватывает новый снимок раз в 30 с, принудительно — `POST /api/v1/predictions/refresh` (роль `dispatcher` или выше).

## Production-стенд

Стенд: https://5bit.online. Подготовка сервера, HTTPS, автодеплой из `main`, откат, загрузка журнала и резервные копии описаны в [infra/README.md](../infra/README.md).

## Локальная разработка без Docker

```bash
docker compose up -d db

cd backend
cp .env.example .env            # задайте VENA_JWT_SECRET: openssl rand -hex 32
uv sync
uv run alembic upgrade head
VENA_SEED_ADMIN=user1 uv run python -m app.db.seed_users
uv run fastapi dev              # http://127.0.0.1:8000

cd ../frontend
cp .env.example .env.local      # NEXT_PUBLIC_VENA_WORKFLOW_MODE=api — работа с backend
pnpm install
pnpm dev                        # http://localhost:3000

cd ../ml
python3 -m venv .venv && . .venv/bin/activate
pip install -r ../infra/docker/ml-requirements.txt   # набор ML-контейнера; с PyTorch и numba — requirements.txt
python score_snapshot.py        # снимок по ml/dataset в results/predictions/snapshot.json; без журнала — --demo
```

## Переменные окружения

Backend читает переменные с префиксом `VENA_` из окружения и `backend/.env`. Полный список — `backend/app/core/config.py`, примеры — `backend/.env.example`, `infra/.env.example` (стенд) и `compose.yaml`.

| Переменная | Назначение |
|---|---|
| `VENA_DATABASE_URL`, `VENA_ENVIRONMENT` | строка подключения `postgresql+psycopg://…`; среда `local`, `test`, `staging`, `production` |
| `VENA_PUBLIC_URL`, `VENA_CORS_ORIGINS` | публичный адрес (ссылки в письмах, проверка Origin, `Secure` у cookie) и разрешённые источники |
| `VENA_AUTH_ENABLED`, `VENA_JWT_SECRET`, `VENA_JWT_TTL_MINUTES` | вход и JWT; секрет не короче 32 байт. В коде вход по умолчанию выключен, в compose и примерах включён |
| `VENA_SEED_USERS`, `VENA_SEED_ADMIN`, `VENA_USER_PASSWORD` | создание `user1`–`user20` при старте контейнера; в локальном compose включено, на стенде выключено |
| `VENA_SEED_DEMO` | демонстрационные работы, уведомления и геослой карты; в compose выключено |
| `VENA_TIMEZONE` | часовой пояс отчётов и журнала, по умолчанию `Europe/Moscow` |
| `VENA_ML_DIR`, `VENA_PREDICTIONS_DIR` | каталог ML и каталог снимка (по умолчанию `VENA_ML_DIR/results/predictions`) |
| `VENA_DATASET_DIR`, `VENA_INBOX_DIR` | каталог журнала и справочника (без него загрузка файлов выключена) и очередь пакетов потока СМВУ, общая с ML-контейнером |
| `VENA_PREDICTION_REFRESH_SECONDS`, `VENA_PREDICTION_STALE_SECONDS`, `VENA_SMVU_STALE_SECONDS` | проверка нового снимка (30 с), возраст снимка до предупреждения (86 400 с), тишина потока СМВУ до правила «Источник недоступен» (900 с) |
| `VENA_UPLOAD_MAX_BYTES`, `VENA_UPLOAD_MAX_ROWS` | лимиты файла: 256 МБ и 1 000 000 строк |
| `VENA_TRUSTED_PROXIES` | прокси, которому доверяется `X-Forwarded-For`; на стенде `["caddy"]` |
| `VENA_LDAP_*`, `VENA_EQUIPMENT_SYNC_*`, `VENA_HELPDESK_*` | интеграции, см. [data-integrations.md](data-integrations.md) |
| `SMTP_*` | почта, см. [email-notifications.md](email-notifications.md) |
| `VENA_ML_MODE`, `VENA_ML_REFRESH_SECONDS`, `VENA_STREAM_POLL_SECONDS` | ML-контейнер: режим `auto` (по умолчанию), `journal` или `demo`; период демо-пересчёта (3600 с) и опроса очереди потока (30 с) |
| `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_VENA_WORKFLOW_MODE` | адрес API и режим интерфейса (`api` или автономный `demo`); задаются при сборке |

## Переобучение моделей

`cd ml && python run_production_refresh.py` заново извлекает события из журнала и переобучает модели. Претендент не заменяет текущую модель, если его AP на отложенном периоде ниже более чем на 0,005. Затем выполняются калибровка, пересчёт аналитики, реестра моделей и снимка (`score_snapshot.py`). Отдельные шаги: `run_final_freeze.py`, `run_pump_blend_freeze.py`, `run_power_freeze.py`, `run_flood_freeze.py`, `run_alarm_freeze.py`, `run_calibration.py`, `run_refit_study.py --promote`, `build_model_registry.py`. Методика описана в [ml/README.md](../ml/README.md#воспроизведение).

## Резервное копирование

На стенде `infra/scripts/backup.sh` запускается таймером systemd `vena-backup.timer` ежедневно в 03:00 UTC. Он сохраняет дамп PostgreSQL, каталог `dataset` и очередь `inbox`; копии хранятся 14 дней. Перед каждым деплоем дополнительно снимается дамп. `infra/scripts/verify-backup.sh <файл.sql.gz>` проверяет копию во временной базе. Восстановление описано в [infra/README.md](../infra/README.md#резервные-копии).

Локальная база (команды из корня репозитория):

```bash
backend/scripts/backup-postgres.sh        # backups/vena-<время>.sql.gz, хранятся 14 последних
docker compose stop backend
docker compose exec -T db dropdb -U vena --force vena
docker compose exec -T db createdb -U vena vena
gunzip -c backups/vena-<время>.sql.gz | docker compose exec -T db psql -U vena -d vena
docker compose start backend
```

### Время восстановления

`infra/scripts/restore-drill.sh` замеряет полный цикл на тестовом стенде: останавливает backend, снимает дамп, удаляет и восстанавливает базу (`pg_restore` и `psql`), сверяет число строк всех таблиц и ждёт, пока backend станет healthy. Аргументы скрипта передаются в `docker compose`, например `infra/scripts/restore-drill.sh -p vena-test -f compose.yaml`. Замер 16.10.2026 на базе 224 МБ (1 млн событий журнала, 337 тыс. оценок прогнозов) показал 21 с от остановки backend до готового API. Требование «восстановление ≤ 4 ч» выполняется с запасом.

## Нагрузочный тест

```bash
VENA_LOAD_PASSWORD=0987654321 python3 infra/scripts/load-test.py \
  --url http://localhost:8100 --users 20 --duration 180 --pause 60
```

Скрипт (только стандартная библиотека Python) входит пользователями `user1`…`userN`, повторяет 12 запросов чтения, которые делает интерфейс, и печатает p50, p95 и max по каждому запросу; при ошибках код выхода 1. Замер 16.10.2026: один процесс backend, полный журнал (10 879 прогнозов), 20 пользователей с частотой опроса интерфейса. Медиана экрана — 0,45 с, p95 — 0,90 с, ошибок 0, как у одного пользователя. Без пауз backend обрабатывает около 33 запросов/с без ошибок.

## Проверки

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
cd emulators/helpdesk && uv run --project ../../backend pytest
```

Тестам backend нужен запущенный PostgreSQL. База `vena_test` создаётся автоматически, адрес переопределяет `VENA_DATABASE_URL`.
