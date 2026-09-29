# Развёртывание Vena

Production-стек: Caddy → Next.js / FastAPI → PostgreSQL 16. Отдельный ML-контейнер
раз в час оценивает каналы замороженными моделями и атомарно обновляет снимок.
Наружу опубликованы только 80/443. PostgreSQL, модели, сертификаты и прогнозы
сохраняются в Docker volumes. Контейнеры запускаются после перезагрузки сервера.

## Настройка сервера

Требуются Docker Engine, Compose v2+, Git, curl, Python 3, tar, gzip и flock.
Создайте пользователя `vena-deploy` с домашним каталогом и членством в группе
`docker` (эта группа даёт привилегии root), добавьте отдельный публичный SSH-ключ
GitHub Actions в его `~/.ssh/authorized_keys`.

```sh
sudo mkdir -p /opt/vena/{incoming,releases,shared/dataset,shared/backups}
sudo chown -R vena-deploy:vena-deploy /opt/vena
sudo chmod 700 /opt/vena/shared
cp infra/.env.example /opt/vena/shared/.env
chmod 600 /opt/vena/shared/.env
```

Замените пароль PostgreSQL и `VENA_JWT_SECRET` разными случайными hex-значениями.
Создание пользователей и роли описаны в [docs/authentication.md](../docs/authentication.md). Не коммитьте `.env` и закрытый
SSH-ключ. `VENA_SITE_ADDRESS=http://5.129.225.86` включает HTTP по IP.
Для HTTPS укажите домен в `VENA_SITE_ADDRESS`, `https://домен` в `VENA_PUBLIC_URL`
и направьте A/AAAA на сервер: Caddy получит и продлит сертификат автоматически.

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
(по умолчанию `http://5.129.225.86`; измените вместе с серверным `.env`).

Workflow передаёт архив точного Git commit по SSH. `infra/scripts/deploy.sh`
блокирует параллельные деплои, собирает образы с тегом SHA, проверяет Caddy,
сохраняет дамп БД перед миграциями, дожидается healthchecks и проверяет API.
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

По умолчанию `VENA_ML_MODE=demo`: синтетические каналы оцениваются настоящими
сохранёнными моделями. Это демонстрационный стенд, не подключение к СМВУ.
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

Для демонстрации потока на уже загруженном журнале задайте `VENA_STREAM_HISTORY_UNTIL=2026-06-01` и воспроизведите последующий период: `python ml/replay_journal.py --url http://5.129.225.86 --start 2026-06-01 --end 2026-06-08` с ключом в `VENA_API_KEY`.

SMTP включается переменными `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TLS` в серверном `.env`. Без SMTP почта
не отправляется; внутренние уведомления сохраняются в БД.

## Резервные копии

```sh
sudo cp infra/systemd/vena-backup.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vena-backup.timer
sudo systemctl start vena-backup.service
```

Ежедневный дамп в 03:00 UTC, хранение 14 дней в `/opt/vena/shared/backups`.
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
