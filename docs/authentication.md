# Вход и пользователи

Вход — по логину или email с паролем либо через LDAP/AD. Публичной регистрации нет.

## Вход и сессии

- Пароли хранятся в PostgreSQL только как хеши Argon2 (pwdlib), длина пароля — от 10 символов.
- После входа выдаётся JWT (HS256, PyJWT): cookie `vena_session` (`HttpOnly`, `SameSite=Lax`,
  `Path=/api/v1`, `Secure` при `https` в `VENA_PUBLIC_URL`) или `Authorization: Bearer` для внешних клиентов.
- На каждом запросе проверяются подпись, срок, сессия в `auth_sessions` и активность; роль и область — из БД.
- Выход отзывает текущую сессию; смена или сброс пароля и изменение роли, блокировки или области — все сессии
  пользователя. Меняющий данные запрос с cookie проверяется по `Origin` (`VENA_PUBLIC_URL`, `VENA_CORS_ORIGINS`).
- Не больше 10 попыток входа на логин и 100 на IP за окно, далее HTTP 429 с `Retry-After`. Вход, неудачные попытки
  (без пароля), выход и смена пароля пишутся в аудит с IP клиента.

Переменные: `VENA_AUTH_ENABLED` (в обоих compose `true`), `VENA_JWT_SECRET` (от 32 байт,
`openssl rand -hex 32`, иначе backend не стартует; на стенде — в `/opt/vena/shared/.env`),
`VENA_JWT_TTL_MINUTES` (60), `VENA_AUTH_LOGIN_LIMIT` (10), `VENA_AUTH_LOGIN_WINDOW_SECONDS` (300),
`VENA_TRUSTED_PROXIES` (от кого принимать `X-Forwarded-For`, на стенде `["caddy"]`).

## Роли

| Роль | Права |
|---|---|
| `viewer` | просмотр экранов и API в пределах своей области |
| `dispatcher` | то же и работы, решения, подтверждение уведомлений, «Взять в работу», приём потока СМВУ |
| `admin` | то же и пользователи, настройки уведомлений, пороги моделей, импорт, геослой, аудит, машина времени; видит все объекты |

## Создание пользователей user1–user20

Скрипт `backend/app/db/seed_users.py` создаёт `user1`…`user20` (`userN@example.com`, роль `dispatcher`, пароль `0987654321`
или `VENA_USER_PASSWORD`); существующие аккаунты не меняются, запуск можно повторять. `VENA_SEED_ADMIN=user1` (`--admin`)
делает аккаунт администратором, `VENA_SEED_SCOPES='{"user18":["complex:5"]}'` задаёт области (по умолчанию `all`). При
`VENA_SEED_USERS=true` скрипт выполняется при старте backend: в корневом compose включено, в `infra/.env.example` выключено.
Флаги: `--count`, `--email-domain`, `--role`; `--username` и `--email` создают один аккаунт.

```sh
cd backend && VENA_SEED_ADMIN=user1 uv run python -m app.db.seed_users   # локально, после alembic upgrade head
export VENA_ENV_FILE=/opt/vena/shared/.env                                # стенд
docker compose --env-file "$VENA_ENV_FILE" -f /opt/vena/current/infra/compose.yaml exec backend python -m app.db.seed_users
```

## Области видимости

Роль определяет, что пользователь может делать, область — какие объекты он видит. Иерархия берётся
из `справочник_объектов_диспетчер.csv` в `VENA_DATASET_DIR` (уровни: 1 — район, 2 — комплекс, 3 — объект),
загрузка — `POST /api/v1/imports?kind=objects`, дерево — `GET /api/v1/objects/tree`.

| Область | Что видно |
|---|---|
| `all` | все объекты |
| `district:<id>` | район со всеми комплексами и объектами, например `district:5773` |
| `complex:<id>` | комплекс и его объекты, например `complex:5` — «объект Альфа» |
| `object:<id>` | один объект, например `object:5122` — «ДУ объект Альфа»; работает и без справочника |

Области суммируются, администратор видит всё. Сервер фильтрует прогнозы, ситуации, работы,
уведомления, журнал, события, аналитику, отчёты, реестр оборудования и геослой; чужой объект даёт 404.
Локальному пользователю область задаёт администратор (колонка «Область» или `PATCH /api/v1/users/{id}`
с `{"scopes": [...]}`). Пользователю LDAP/AD она вычисляется из групп при каждом входе.

## LDAP / Active Directory

| Переменная | Назначение (по умолчанию) |
|---|---|
| `VENA_LDAP_ENABLED`, `VENA_LDAP_URL` | включение (`false`); `ldaps://host:636` или `ldap://host:389` с обязательным StartTLS |
| `VENA_LDAP_BIND_DN`, `VENA_LDAP_BIND_PASSWORD`, `VENA_LDAP_BASE_DN`, `VENA_LDAP_USER_FILTER` | служебная учётная запись, база и фильтр поиска с `{login}` |
| `VENA_LDAP_USERNAME_ATTRIBUTE`, `VENA_LDAP_ID_ATTRIBUTE` | логин и устойчивый ID (`sAMAccountName`, `objectGUID`) |
| `VENA_LDAP_GROUP_ROLES`, `VENA_LDAP_DEFAULT_ROLE` | JSON «DN группы → роль», берётся старшая; роль без группы (`viewer`, `none` — вход запрещён) |
| `VENA_LDAP_GROUP_SCOPES`, `VENA_LDAP_DEFAULT_SCOPES` | JSON «DN или CN группы → области», области суммируются; без совпадений (`["all"]`) |
| `VENA_LDAP_CA_FILE`, `VENA_LDAP_TIMEOUT_SECONDS` | CA каталога в PEM, тайм-аут (5 с) |

Сертификат и имя сервера проверяются всегда. При первом входе создаётся запись `ldap:<логин>`, пароль
каталога не хранится. Пример для AD — в [data-integrations.md](data-integrations.md#ldap--active-directory-тз-11).

## Тестовый каталог LDAP

`VENA_LDAP_ENABLED=true docker compose --profile ldap up -d` поднимает OpenLDAP (`osixia/openldap:1.5.0`).
Контейнер `ldap-certs` (`emulators/ldap/make-certs.sh`) выпускает тестовый CA и сертификат хоста `ldap`;
backend получает только `ca.crt` и подключается через StartTLS. Пользователи — `emulators/ldap/ldif/users.ldif`,
пароль у всех `vena-ldap-test`, вход по `uid` или email: `ldap-admin` (группа `cn=vena-admins`, роль `admin`),
`ldap-dispatcher` (`cn=vena-dispatchers`, `dispatcher`), `ldap-viewer` (`cn=vena-viewers`, `viewer`).

## API

| Запрос | Доступ | Назначение |
|---|---|---|
| `POST /api/v1/auth/login`, `POST /api/v1/auth/ldap` | все | `email` (или `login`) и `password`; ответ — `access_token`, `expires_in`, `user` и cookie |
| `GET /api/v1/auth/me`, `GET /api/v1/auth/status` | вошедший; все | текущий пользователь с `scopes`; включён ли вход и доступен ли LDAP |
| `POST /api/v1/auth/logout`, `POST /api/v1/auth/password` | вошедший | отзыв сессии; смена пароля (`current_password`, `new_password`) |
| `GET`, `POST /api/v1/users`; `PATCH /api/v1/users/{id}`; `POST /api/v1/users/{id}/password` | `admin` | список, создание, изменение, сброс пароля |
