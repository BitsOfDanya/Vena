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

Из корня репозитория одна команда:

```bash
docker compose up -d --build
```

Поднимаются пять контейнеров: `db` (PostgreSQL), `ml` (ML-воркер), `backend`, `frontend` и `helpdesk` (эмулятор системы заявок). Первая сборка образов занимает около 10 минут (скачиваются образы Python, Node.js и ML-библиотеки), повторный запуск — около минуты. Стенд готов, когда `docker compose ps` показывает все сервисы `healthy`; с флагом `--wait` команда сама дождётся готовности.

| Сервис | Адрес |
|---|---|
| Интерфейс | http://localhost:3100 |
| API и OpenAPI | http://localhost:8100/docs |
| PostgreSQL | 127.0.0.1:5432 (порт на хосте меняет `VENA_DB_PORT`) |
| Эмулятор системы заявок и учётной системы | http://localhost:8090 (`VENA_HELPDESK_PORT`), [data-integrations.md](data-integrations.md#эмуляторы-внешних-систем) |
| Тестовый каталог LDAP | профиль `ldap`, [authentication.md](authentication.md#тестовый-каталог-ldap) |

Вход: `user1` / `0987654321` — администратор, `user2`–`user20` с тем же паролем — диспетчеры. Учётные записи создаются при первом старте (`VENA_SEED_USERS=true`, `VENA_SEED_ADMIN=user1`, пароль меняет `VENA_USER_PASSWORD`). Повторный старт существующие учётные записи не меняет.

Что происходит при старте:

- `ml` (`VENA_ML_MODE=auto`) смотрит в `ml/dataset`. Если там есть журнал `ext-journal-*.csv` и `справочник_каналов_датчиков.csv`, считает прогнозы по реальным каналам. Иначе публикует демонстрационный снимок тех же замороженных моделей по синтетическим каналам насосов, вентиляторов и дымовых датчиков. Снимок лежит в томе `vena-predictions`.
- `backend` ждёт базу и `ml`, применяет миграции, создаёт пользователей и раз в 30 с подхватывает новый снимок. `ml/results`, `ml/configs`, `ml/artifacts` и том снимка смонтированы только на чтение.
- Загрузка CSV/XLSX в интерфейсе пишет файлы в тот же `ml/dataset`, и `ml` без перезапуска переходит на реальный журнал. Пакеты потока СМВУ попадают в том `vena-inbox` и обрабатываются, когда журнал загружен.

Другой каталог журнала задаёт `VENA_DATASET_DIR`. Если каталога нет, Docker создаёт его сам (на Linux — от root), поэтому журнал удобнее положить до первого запуска. Порты на хосте меняют `VENA_UI_PORT`, `VENA_API_PORT` и `VENA_DB_PORT`. Адрес API вшивается в интерфейс при сборке, поэтому после смены `VENA_API_PORT` нужен `--build`. Остановка — `docker compose down`, с удалением базы и снимка — `docker compose down -v`. Пользователи и роли — [authentication.md](authentication.md).

## Снимок прогнозов

Снимок не хранится в репозитории: он строится из журнала СМВУ, а журнал не распространяется. В Docker его строит контейнер `ml`. Без Docker — вручную.

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
VENA_SEED_ADMIN=user1 uv run python -m app.db.seed_users
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
| `VENA_SEED_USERS`, `VENA_SEED_ADMIN`, `VENA_USER_PASSWORD` | создать `user1`–`user20` при старте контейнера; указанный в `VENA_SEED_ADMIN` пользователь создаётся администратором. В локальном compose включено, на стенде выключено |
| `VENA_SEED_DEMO` | демонстрационные работы, уведомления и геослой карты |
| `VENA_ML_DIR` | каталог ML (снимок, реестр моделей, результаты) |
| `VENA_PREDICTIONS_DIR` | каталог снимка прогнозов, если он не `VENA_ML_DIR/results/predictions` |
| `VENA_TRUSTED_PROXIES` | адреса, подсети или имена обратного прокси, которому доверяется `X-Forwarded-For` (IP в аудите и ограничении входа); на стенде `["caddy"]` |
| `VENA_DATASET_DIR` | каталог принятых загрузок CSV/XLSX; без него импорт через интерфейс выключен |
| `VENA_INBOX_DIR` | очередь пакетов потока СМВУ для ML-контейнера |
| `VENA_PREDICTION_REFRESH_SECONDS` | период проверки нового снимка, 30 с |
| `VENA_PREDICTION_STALE_SECONDS` | возраст снимка, после которого показывается предупреждение |
| `VENA_SMVU_STALE_SECONDS` | тишина потока СМВУ, после которой срабатывает правило «Источник недоступен», 900 с |
| `VENA_PREDICTION_CRITICAL_LIMIT`, `VENA_PREDICTION_COOLDOWN_MINUTES` | лимит уведомлений на сценарий и пауза повторов |
| `VENA_EQUIPMENT_SYNC_*` | синхронизация реестра с учётной системой |
| `VENA_HELPDESK_URL`, `VENA_HELPDESK_TOKEN`, `VENA_HELPDESK_INTERVAL_SECONDS` | система учёта заявок; пустой адрес выключает интеграцию, см. [data-integrations.md](data-integrations.md#система-учёта-заявок-тз-6) |
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

### Время восстановления

`infra/scripts/restore-drill.sh` замеряет полный цикл на **тестовом** стенде: останавливает
backend, снимает дамп в двух форматах (`pg_dump -Fc` и SQL + gzip, как `backup.sh`), дважды
удаляет и восстанавливает базу (`pg_restore` и `psql`), сверяет число строк каждой таблицы и
запускает backend до healthy. Аргументы передаются `docker compose`:

```bash
infra/scripts/restore-drill.sh -p vena-test -f compose.yaml
```

Замер 16.10.2026: корневой compose, Apple M3 Pro, PostgreSQL 16. База 224 МБ: 1 000 000 событий
журнала (около месяца потока), 337 278 оценок прогнозов (30 суточных пересчётов снимка на
10 879 прогнозов), 23 пользователя, реестр, работы с заявками, уведомления, аудит.
Объём добавлен так:

```sql
INSERT INTO historical_events (event_id, channel_id, ts, value, alarm)
SELECT 'drill-' || g, (100000 + g % 10879)::text, now() - interval '30 days' + g * interval '2.592 seconds',
       (ARRAY['Норма','Неисправен','Обесточен','Сработал'])[1 + g % 4], g % 7 = 0
FROM generate_series(1, 1000000) AS g;
```

| Шаг | Время, с | Размер |
|---|---|---|
| остановка backend | 1,8 | |
| `pg_dump -Fc` | 2,1 | 17 МБ |
| `pg_dump` + gzip, как `backup.sh` | 2,5 | 17 МБ |
| `dropdb`, `createdb`, `pg_restore` | 7,8 | |
| `dropdb`, `createdb`, `gunzip`, `psql` | 7,9 | |
| запуск backend до healthy | 11,2 | |
| **от остановки до готового API** | **20,8–20,9** | |

Требование «восстановление ≤ 4 ч» выполняется с большим запасом. На стенде к этому времени
добавляются копирование файла копии и распаковка архивов `dataset` и `inbox`
([infra/README.md](../infra/README.md#резервные-копии)).

## Нагрузочный тест

`infra/scripts/load-test.py` (только стандартная библиотека Python) входит пользователями
`user1`…`userN` и повторяет 12 запросов чтения, которые делает интерфейс: пользователь,
состояние снимка, сводка и страница из 5000 прогнозов, ситуации, работы, уведомления, журнал и
его сводка, статистика по типам, лента событий, системные уведомления. `--pause` — пауза между
повторами (±50 %, пользователи стартуют вразнобой), `0` — без пауз. Печатает p50/p95/max по
каждому запросу, ошибки и запросы в секунду; при ошибках код выхода 1.

```bash
VENA_LOAD_PASSWORD=0987654321 python3 infra/scripts/load-test.py \
  --url http://localhost:8100 --users 20 --duration 180 --pause 60
```

Замер 16.10.2026: корневой compose (один процесс uvicorn, PostgreSQL 16), Apple M3 Pro,
Docker 12 CPU. Интерфейс обновляет дашборд, сводку и журнал раз в 60 с, колокольчик — раз
в 15 с. «Экран» — все 12 запросов одного пользователя подряд; браузер выполняет их
параллельно, поэтому это верхняя оценка.

| Снимок | Пользователи, пауза | Запросов / ошибок | 5000 прогнозов p50 / p95, мс | Экран p50 / p95, мс | Запросов/с |
|---|---|---|---|---|---|
| полный журнал, 10 879 прогнозов | 1, 5 с | 132 / 0 | 240 / 381 | 571 / 823 | 2,2 |
| полный журнал, 10 879 прогнозов | 20, 60 с — как интерфейс | 660 / 0 | 177 / 439 | 446 / 897 | 3,7 |
| полный журнал, 10 879 прогнозов | 20, 15 с | 1 764 / 0 | 320 / 1 018 | 916 / 2 644 | 14,7 |
| полный журнал, 10 879 прогнозов | 20, без пауз | 2 064 / 0 | 947 / 3 050 | 6 914 / 9 177 | 33,2 |
| демонстрационный, 29 прогнозов | 20, 5 с | 2 676 / 0 | 7 / 32 | 110 / 650 | 44,6 |
| демонстрационный, 29 прогнозов | 20, без пауз | 13 200 / 0 | 71 / 183 | 991 / 1 671 | 217,9 |

20 пользователей с частотой опроса интерфейса, полный журнал, мс:

| Запрос | p50 | p95 | max |
|---|---|---|---|
| `/auth/me` | 30 | 54 | 109 |
| `/predictions/snapshot` | 10 | 19 | 22 |
| `/predictions/summary?horizon=24&top=5` | 36 | 57 | 86 |
| `/predictions?horizon=24&sort=risk_desc&limit=5000` | 177 | 439 | 504 |
| `/situations` | 62 | 127 | 317 |
| `/actions` | 13 | 27 | 60 |
| `/notifications?limit=100` | 8 | 21 | 79 |
| `/journal?limit=2000` | 15 | 38 | 48 |
| `/journal/summary` | 12 | 28 | 81 |
| `/analytics/event-types` | 39 | 79 | 108 |
| `/events/recent?hours=6&limit=60` | 9 | 29 | 43 |
| `/system/notices` | 8 | 17 | 37 |

При частоте опроса интерфейса 20 пользователей получают те же времена, что один. Ошибок нет
ни в одном сценарии. Предел одного процесса backend на полном снимке — около 33 запросов в
секунду, это в 9 раз больше нагрузки 20 пользователей; дальше запросы ждут в очереди.

## Проверки

```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest
cd frontend && pnpm lint && pnpm typecheck && pnpm test && pnpm build
cd ml && python -m pytest
cd emulators/helpdesk && pytest
```

Тестам backend нужен запущенный PostgreSQL; база `vena_test` создаётся автоматически (`VENA_DATABASE_URL` переопределяет адрес).
