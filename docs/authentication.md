# Вход и пользователи

Вход доступен по email **или** логину и паролю. Пароли хранятся в PostgreSQL
только как Argon2-хеши с индивидуальной солью. Роли: `viewer` — чтение,
`dispatcher` — работы и решения, `admin` — настройки, аудит и геоданные.
Публичная регистрация не включена: аккаунты создаются административным скриптом.

## Конфигурация

Задайте `VENA_AUTH_ENABLED=true` и случайный `VENA_JWT_SECRET` длиной не менее
32 байт (`openssl rand -hex 32`). На сервере это `/opt/vena/shared/.env`.
Секрет не хранится в Git. При отсутствии секрета включённая аутентификация
не допускает запуск приложения. `VENA_JWT_TTL_MINUTES=60` задаёт срок JWT.
Значение секрета по умолчанию в корневом Compose — только для локальной разработки.

Браузер хранит JWT в cookie `vena_session` с `HttpOnly`, `SameSite=Lax` и
`Path=/api/v1`. При `VENA_PUBLIC_URL=https://…` добавляется `Secure`.
JWT не сохраняется в localStorage; старый API-ключ удаляется браузером.
Production доступен по `https://5bit.online`; cookie сессии передаётся только
по HTTPS. При смене домена обновите адрес Caddy и `VENA_PUBLIC_URL`,
чтобы защищённые cookie и проверка Origin использовали новый адрес.

Проверяются HS256-подпись, `exp`, `nbf`, `iat`, issuer, audience, тип токена,
существование сессии и активность пользователя. Роль берётся из БД.
Выход немедленно отзывает текущую сессию, смена пароля — все сессии пользователя.
По истечении JWT нужен повторный вход. Refresh-токены не используются.
Для меняющих данные запросов с cookie требуется разрешённый Origin:
`VENA_PUBLIC_URL` либо `VENA_CORS_ORIGINS`.

Ограничение входа хранится в PostgreSQL: по умолчанию 10 попыток на логин
и 100 на IP за 300 секунд. Ответ — HTTP 429 с Retry-After. Параметры:
`VENA_AUTH_LOGIN_LIMIT`, `VENA_AUTH_LOGIN_WINDOW_SECONDS`.

## Создание 20 пользователей

Локально, после `alembic upgrade head`:

```sh
cd backend
uv run python -m app.db.seed_users
```

Через production Compose:

```sh
export VENA_ENV_FILE=/opt/vena/shared/.env
docker compose --env-file "$VENA_ENV_FILE" -f /opt/vena/current/infra/compose.yaml \
  exec backend python -m app.db.seed_users
```

Создаются ровно 20 аккаунтов: `user1`–`user20`, email
`user1@example.com`–`user20@example.com`, пароль `0987654321`, роль `dispatcher`.
Адреса — демонстрационные, письма для подтверждения не отправляются.
Скрипт повторяемый: существующие пароли, роли и блокировки не изменяются.
Можно задать `--email-domain`, `--count`, `--role`; переменная `VENA_USER_PASSWORD`
переопределяет пароль. `VENA_SEED_USERS=true` явно включает сидирование при старте
контейнера; после первого запуска этот флаг можно выключить.

Отдельная учётная запись, в том числе администратор (пароль вводится скрыто):

```sh
uv run python -m app.db.seed_users --username admin --email admin@example.com --role admin
```

## API

`POST /api/v1/auth/login`:

```json
{"email":"user1@example.com","password":"0987654321"}
```

В поле `email` можно передать `user1`; также поддерживается поле `login`.
Ответ содержит `access_token`, `token_type=bearer`, `expires_in` и `user`.
Для внешних клиентов передавайте `Authorization: Bearer <access_token>`.

- `GET /api/v1/auth/me` — пользователь и роль.
- `POST /api/v1/auth/logout` — отзыв текущего токена.
- `POST /api/v1/auth/password` — `current_password` и `new_password` (от 10 символов).
- `GET /api/v1/auth/status` — публичное состояние механизма входа.

Старые `X-API-Key` и API-ключи в Bearer больше не действуют.
После обновления пользователям нужно войти заново.

Проверки автодеплоя создают временных пользователей со случайными паролями,
проверяют вход, JWT, роли и отзыв сессии, затем удаляют эти аккаунты.

Реализация использует [PyJWT](https://pyjwt.readthedocs.io/en/stable/usage.html)
и [pwdlib/Argon2, описанные в документации FastAPI](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/).
