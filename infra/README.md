# Развёртывание Vena

Production-стек: Caddy → Next.js / FastAPI → PostgreSQL 16. Отдельный ML-контейнер
оценивает каналы замороженными моделями и атомарно обновляет снимок: по журналу —
на каждый пакет потока, без журнала — демонстрационный снимок раз в час.
Наружу опубликованы только 80/443. PostgreSQL, прогнозы и очередь потока хранятся
в Docker volumes, журнал и сертификаты LDAP — в `/opt/vena/shared`, модели входят в образы. Контейнеры запускаются после перезагрузки сервера.

## Настройка сервера

Требуются Docker Engine, Compose v2+, Git, curl, Python 3, tar, gzip и flock.
Создайте пользователя `vena-deploy` с домашним каталогом и членством в группе
`docker` (эта группа даёт привилегии root), добавьте отдельный публичный SSH-ключ
GitHub Actions в его `~/.ssh/authorized_keys`.

```sh
sudo mkdir -p /opt/vena/{incoming,releases,shared/dataset,shared/backups}
sudo chown -R vena-deploy:vena-deploy /opt/vena
sudo chmod 700 /opt/vena/shared
sudo chown 10001:$(id -g vena-deploy) /opt/vena/shared/dataset
sudo chmod 2775 /opt/vena/shared/dataset
sudo mkdir -p /opt/vena/shared/certs
cp infra/.env.example /opt/vena/shared/.env
chmod 600 /opt/vena/shared/.env
```

Замените пароль PostgreSQL и `VENA_JWT_SECRET` разными случайными hex-значениями.
Создание пользователей и роли описаны в [docs/authentication.md](../docs/authentication.md). Не коммитьте `.env` и закрытый
SSH-ключ. Рабочий адрес сервиса — `https://5bit.online`.
В серверном `.env` заданы `VENA_SITE_ADDRESS=5bit.online` и
`VENA_PUBLIC_URL=https://5bit.online`; A-запись домена указывает на `5.129.225.86`.
Caddy автоматически получает и продлевает сертификат, перенаправляет HTTP на HTTPS.
При смене домена обновите DNS, обе переменные и переменную репозитория
`VENA_PUBLIC_URL`, затем пересоздайте Caddy и backend.

```sh
export VENA_ENV_FILE=/opt/vena/shared/.env
docker compose --env-file "$VENA_ENV_FILE" -f infra/compose.yaml up -d --build --wait
```

## Автодеплой

`.github/workflows/deploy.yml` запускается при push в `main` и вручную через
Actions → Deploy Vena → Run workflow. Секреты репозитория:

- `VENA_DEPLOY_KEY`: закрытый ключ пользователя `vena-deploy`.
- `VENA_KNOWN_HOSTS`: проверенная запись SSH host key сервера.

Переменные: `VENA_DEPLOY_HOST` (по умолчанию `5.129.225.86`), `VENA_PUBLIC_URL`
(по умолчанию `https://5bit.online`; измените вместе с серверным `.env`).

Workflow передаёт архив точного Git commit по SSH. `infra/scripts/deploy.sh`
блокирует параллельные деплои, собирает образы с тегом SHA, проверяет Caddy,
сохраняет дамп БД перед миграциями, дожидается healthchecks и проверяет API.
При ограничении реестра (`429 Too Many Requests`) сборка повторяется с базовыми
образами Node.js и Python из [кэша Google `mirror.gcr.io`](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images).
Если повторная сборка не удаётся, работающие контейнеры остаются на месте.
Успешный SHA хранится в `/opt/vena/deployed-revision`, текущий релиз — в
`/opt/vena/current`. Сборка завершается до замены работающих контейнеров;
при их пересоздании возможен короткий перерыв в обслуживании.

Если запуск или smoke-проверка не прошли, восстанавливаются контейнеры предыдущего
релиза. Миграции БД автоматически не откатываются: новые миграции должны быть
совместимы с предыдущим релизом. Для несовместимых изменений восстановите дамп
вручную. Первому деплою откатываться некуда.

```sh
# Ручной запуск уже загруженного релиза
bash /opt/vena/deploy.sh <40-символьный-sha>
# Статус и логи
export VENA_ENV_FILE=/opt/vena/shared/.env
export VENA_REVISION=$(cat /opt/vena/deployed-revision)
docker compose --env-file "$VENA_ENV_FILE" -f /opt/vena/current/infra/compose.yaml ps
docker compose --env-file "$VENA_ENV_FILE" -f /opt/vena/current/infra/compose.yaml logs --tail=100
```

## Данные и проверки

По умолчанию `VENA_ML_MODE=auto`: сервис ожидает реальный справочник и журнал, а пока их нет, показывает демонстрационный снимок с пометкой `data_source=demo`. Во время пересчёта журнала остаётся предыдущий снимок, новый публикуется атомарно.
Загрузка доступна администратору в настройках; [инструкция](../docs/data-integrations.md).
Режим `demo` включается явно и отмечается в интерфейсе.
Для журнала поместите исходные CSV в `/opt/vena/shared/dataset`, установите
`VENA_ML_MODE=journal` и перезапустите ML. Снимок публикуется атомарно, backend
подхватывает его по расписанию; обработку можно вызвать через
`POST /api/v1/predictions/refresh` с ролью dispatcher/admin.

`infra/scripts/smoke.py` проверяет health, вход, отказ без ключа, RBAC, наличие
прогнозов, чтение работ/журнала/геоданных и запись результатов refresh в БД.
Workflow дополнительно проверяет публичные `/pulse` и `/api/v1/health` через Caddy.

### Журнал СМВУ и поток событий

Загрузка журнала и включение режима `journal` одной командой со своего компьютера (нужен SSH-доступ `vena-deploy`):

```sh
infra/scripts/upload-dataset.sh --enable vena-deploy@5.129.225.86
```

Скрипт копирует `ml/dataset/ext-journal-*.csv` и справочник каналов в `/opt/vena/shared/dataset`, выставляет `VENA_ML_MODE=journal` и перезапускает `ml` и `backend`. В режиме `journal` ML-контейнер один раз оценивает журнал целиком (десятки минут, в это время API отвечает «Predictions unavailable»), затем работает как поток:

- СМВУ передаёт события в `POST /api/v1/smvu/events` (роль dispatcher или admin): `batch_id`, `event_count` и массив `events` из записей `event_id`, `channel_id`, `ts`, `value`, `alarm` — формат Приложения 1 ТЗ.
- API кладёт батч в общий том `inbox`; ML каждые `VENA_STREAM_POLL_SECONDS` (30 с) пересчитывает только каналы с новыми событиями и публикует снимок; backend забирает снимок каждые 30 с. Задержка потока видна в `GET /api/v1/predictions/snapshot` → `stream.latency_seconds`.
- По мере поступления событий прогнозы, выданные после конца журнала, сверяются с фактом: `GET /api/v1/ml/prospective`.
- Раз в сутки выполняется полный пересчёт, включая разделы тревог и доступа.

Для демонстрации потока на уже загруженном журнале задайте `VENA_STREAM_HISTORY_UNTIL=2026-06-01` и воспроизведите последующий период: `python ml/replay_journal.py --url https://5bit.online --start 2026-06-01 --end 2026-06-08` с JWT пользователя роли `dispatcher` в `VENA_TOKEN` (`access_token` из `POST /api/v1/auth/login`).

SMTP включается переменными `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS`, `SMTP_SECURE` в серверном `.env`, подробно —
[email-notifications.md](../docs/email-notifications.md). Без SMTP письма ждут в очереди,
уведомления в интерфейсе работают.

## Резервные копии

```sh
sudo cp infra/systemd/vena-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vena-backup.timer
sudo systemctl start vena-backup.service
```

Ежедневно в 03:00 UTC `infra/scripts/backup.sh` сохраняет дамп PostgreSQL, каталог `dataset` и очередь `inbox` в `/opt/vena/shared/backups`, хранение 14 дней. `infra/scripts/verify-backup.sh <файл.sql.gz>` восстанавливает дамп во временную базу и проверяет число строк, не трогая рабочую.
Это локальные копии; для защиты от потери VPS копируйте их на отдельный сервер.
Перед восстановлением остановите backend, затем:

```sh
gunzip -c /opt/vena/shared/backups/vena-<timestamp>.sql.gz | \
  docker compose --env-file "$VENA_ENV_FILE" -f /opt/vena/current/infra/compose.yaml \
  exec -T db psql -U vena -d vena
```

Старые образы удаляйте после проверки релиза. Не удаляйте образы текущего и
предыдущего SHA, если нужен быстрый откат. `docker compose down -v` удаляет данные.

Документация: [Caddy HTTPS](https://caddyserver.com/docs/automatic-https),
[Compose healthchecks](https://docs.docker.com/compose/how-tos/startup-order/),
[Next.js standalone](https://nextjs.org/docs/app/api-reference/config/next-config-js/output).
