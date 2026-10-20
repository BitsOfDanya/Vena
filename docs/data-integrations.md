# Загрузка данных и корпоративные интеграции

## Журнал и справочник через интерфейс

Загрузка доступна администратору в разделе **Настройки → Интеграции** (`/settings/integrations`):

1. Выберите «Справочник каналов», скачайте шаблон XLSX, заполните его и загрузите CSV или XLSX.
2. После проверки система покажет ошибочные строки (первые 100; в счётчике учтены все). Файл с ошибками не применяется: исправьте его и загрузите заново.
3. Нажмите «Применить загрузку». В истории видно число добавленных, обновлённых и уже существующих записей.
4. Тем же способом загрузите «Журнал событий».

Форматы: CSV в UTF-8 (BOM допускается) с разделителем `,`, `;` или табуляцией; XLSX — один лист, заголовки в первой строке, без формул и макросов. Идентификаторы храните как текст, иначе Excel потеряет ведущие нули. Ограничения: 256 МБ и 1 000 000 строк на файл (`VENA_UPLOAD_MAX_BYTES`, `VENA_UPLOAD_MAX_ROWS`). Большой журнал загружайте частями.

| Колонка справочника | Поле API | Смысл |
|---|---|---|
| `ид_канала_данных` | `asset_id` | идентификатор канала, до 32 символов |
| `название_датчика` | `name` | название оборудования |
| `тип_датчика` | `equipment_type` | тип датчика по справочнику СМВУ |
| `тег_инженерной_системы` | `tag` | тег локации |
| `тип_инж_системы` | `system_type` | инженерная система |
| `ид_объект` | `object_id` | идентификатор объекта |

Необязательные поля: `external_id` (по умолчанию совпадает с каналом), `section`, `manufacturer`, `model`, `serial_number`, `installed_on` (YYYY-MM-DD), `status` (`active`, `maintenance`, `retired`). Записи, которых нет в новой выгрузке, не удаляются: вывод из эксплуатации задаётся явно через `status=retired`. Один `external_id` нельзя перенести на другой канал.

Колонки журнала (приложение 1 ТЗ): `ид_события`, `ид_канала_данных`, `дата` (YYYY-MM-DD), `время` (HH:MM:SS), `тревожное` (t/f, true/false, 1/0, да/нет), `значение_датчика`. Вместо них можно использовать поля API: `event_id`, `channel_id`, `ts` (ISO 8601), `alarm`, `value`. Время без часового пояса трактуется в `VENA_TIMEZONE`. События по каналам, которых нет в справочнике, отклоняются. Повтор уже записанного события пропускается. Если `event_id` совпадает, а содержимое другое, отклоняется вся загрузка.

API (префикс `/api/v1`; загрузка и изменение реестра — роль `admin`, чтение — любая роль):

| Запрос | Назначение |
|---|---|
| `POST /imports?kind=channels\|journal\|objects` | загрузка файла (`multipart/form-data`, поле `file`): проверка, ответ с ID загрузки |
| `POST /imports/{id}/apply` | атомарное применение; повторный вызов безопасен |
| `GET /imports/template/{kind}.xlsx` | шаблон |
| `GET /integrations/status` | состояние ML, счётчики, очередь публикаций, последние 20 запусков |
| `GET /equipment?q=…&offset=0&limit=50` | реестр с поиском |
| `PUT /equipment` | JSON `{"items": [...]}`: обновление реестра без загрузки файла |

`kind=objects` загружает справочник объектов (`ид_объект`, `иерархия_уровень`, `диспетчерское_название_объекта`) и доступен только через API.

## Передача в ML и поток СМВУ

После фиксации транзакции очередь публикаций записывает данные в `VENA_DATASET_DIR`: журнал — в `uploads/ext-journal-<id>.csv`, справочник — в `справочник_каналов_датчиков.csv`, метку версии — в `.revision`. При сбое публикация повторяется через 10 с. ML-контейнер в режиме `auto` замечает изменения и пересчитывает журнал без перезапуска, при этом предыдущий снимок остаётся доступен. Прогноз строится для канала с поддерживаемым типом датчика и не менее чем 20 событиями. Загрузка справочника сама по себе прогнозов не создаёт, обученные модели при импорте не переобучаются. Пока журнала нет, снимок помечен `data_source=demo`; после обработки — `data_source=journal`. Состояние обработки показывает `worker.state` в `GET /integrations/status`.

На стенде каталог журнала — `/opt/vena/shared/dataset`, он должен быть доступен на запись пользователю с UID 10001. Секреты интеграций хранятся только в серверном `.env`, сертификаты — в `/opt/vena/shared/certs` (в контейнере — `/srv/certs`).

Новые события принимает `POST /api/v1/smvu/events` (роль `dispatcher` или `admin`) в JSON или XML (`Content-Type: application/xml`). Обе формы проходят одинаковые проверки:

```json
{"batch_id": "smvu-0001", "event_count": 1, "events": [
  {"event_id": "1", "channel_id": "96463", "ts": "2026-07-01T09:00:00", "value": "Неисправен", "alarm": true}]}
```

```xml
<batch id="smvu-0001" event_count="1">
  <event event_id="1" channel_id="96463" ts="2026-07-01T09:00:00" alarm="true">Неисправен</event>
</batch>
```

- Ответ `202` возвращает состояние источника; `last_event_count` — число новых принятых событий. Пакет без `events` только отмечает, что источник активен.
- Пакеты идемпотентны: событие с уже известным `event_id` и теми же полями пропускается, с другими полями — `409`. Неизвестный канал тоже даёт `409`.
- XML разбирается через defusedxml: DTD, сущности и любые элементы, кроме `<batch>` и `<event>`, отклоняются с `422`.
- События и задание на публикацию сохраняются в одной транзакции, затем попадают в очередь `VENA_INBOX_DIR`. ML опрашивает её каждые `VENA_STREAM_POLL_SECONDS` (30 с) и пересчитывает только затронутые каналы.

Контроль: `GET /api/v1/smvu/status` (последний пакет и свежесть потока), `GET /api/v1/predictions/snapshot` → `stream.latency_seconds`, `GET /api/v1/ml/prospective` (сверка выданных прогнозов с последующими событиями). Лента «Пульс» показывает принятые события через `GET /api/v1/events/recent`. Воспроизведение журнала как потока (`ml/replay_journal.py`) описано в [infra/README.md](../infra/README.md#журнал-смву-и-поток-событий). `infra/scripts/verify-stream.py` проверяет цепочку «справочник → прогноз → новое событие → пересчёт» на изолированных синтетических данных и не подтверждает подключение журнала заказчика.

## Синхронизация с учётной системой (ТЗ 10)

Коннектор только читает данные: выполняет GET к HTTPS JSON API с Bearer-токеном и пагинацией по `cursor`. Протокол в ТЗ не задан; для 1С/OData или другой схемы нужен адаптер к этому формату.

```dotenv
VENA_EQUIPMENT_SYNC_ENABLED=true
VENA_EQUIPMENT_SYNC_URL=https://accounting.example/api/equipment
VENA_EQUIPMENT_SYNC_TOKEN=replace-on-server
VENA_EQUIPMENT_SYNC_SOURCE=customer
VENA_EQUIPMENT_SYNC_INTERVAL_SECONDS=900
VENA_EQUIPMENT_SYNC_FIELD_MAP={"asset_id":"channel.id","external_id":"id","name":"title","object_id":"object.id"}
VENA_EQUIPMENT_SYNC_CA_FILE=/srv/certs/customer-ca.pem
```

Ответ — массив записей или `{"items": [...], "next_cursor": "..."}`. Следующая страница запрашивается с `?cursor=…`, пустой `next_cursor` означает конец. Обязательные поля: `asset_id`, `external_id`, `name`, `object_id`; для прогнозов также нужны `equipment_type`, `tag` и `system_type`. Если задан `FIELD_MAP`, берутся только перечисленные в нём поля, поэтому в карту нужно включить все нужные поля.

Ограничения: 20 с на сетевую операцию, 10 МБ на страницу, 100 страниц, 100 000 каналов. Редиректы запрещены, сертификат проверяется. HTTP разрешён только при `VENA_EQUIPMENT_SYNC_ALLOW_HTTP=true` (для тестового контура). При ошибке реестр не меняется, а причина без токена пишется в историю. Ручной запуск — кнопка «Синхронизировать реестр» или `POST /api/v1/equipment/sync` (роль `admin`).

## Система учёта заявок (ТЗ 6)

Утверждённая работа отправляется заявкой во внешнюю систему, а статус заявки записывается в историю работы. Протокол в ТЗ не задан; реализован HTTPS JSON API с Bearer-токеном из двух вызовов:

- `POST {VENA_HELPDESK_URL}/tickets` с полями `external_ref` (ID работы), `title`, `description` (причина, объект, канал, приоритет, срок), `priority` (`high`, `medium`, `low`), `due_at` (ISO 8601). Ответ — `{"id": …, "status": …}`. `external_ref` служит ключом идемпотентности: повтор для той же работы должен вернуть существующую заявку.
- `GET {VENA_HELPDESK_URL}/tickets/{id}` возвращает `{"id": …, "status": …}`.

Заявка создаётся, когда утверждают черновик работы или сразу создают запланированную работу. Если система недоступна, работа сохраняется, заявка получает статус `pending`, а отправку повторяет планировщик. Он же каждые `VENA_HELPDESK_INTERVAL_SECONDS` (60 с) опрашивает незакрытые заявки. Статусы: `new` — зарегистрирована, `accepted` — принята, `in_progress` — в работе, `closed` — закрыта; другие значения записываются как есть. Закрытие заявки не закрывает работу: результат фиксирует диспетчер. В API работ есть поля `helpdesk_ticket_id` и `helpdesk_status`.

```dotenv
VENA_HELPDESK_URL=https://servicedesk.example/api
VENA_HELPDESK_TOKEN=replace-on-server
VENA_HELPDESK_INTERVAL_SECONDS=60
VENA_HELPDESK_CA_FILE=/srv/certs/customer-ca.pem
```

Пустой `VENA_HELPDESK_URL` выключает интеграцию. Требования к соединению: только HTTPS (HTTP — при `VENA_HELPDESK_ALLOW_HTTP=true`), без редиректов, с проверкой сертификата, 5 с на запрос.

## Эмуляторы внешних систем

Внешние взаимодействия проверяются на эмуляторах из `emulators/`. Корневой `compose.yaml` поднимает их вместе с сервисом.

| Сервис | Что эмулирует | Адрес |
|---|---|---|
| `helpdesk` (`emulators/helpdesk`) | систему заявок и учётную систему | http://127.0.0.1:8090 (`VENA_HELPDESK_PORT`), в сети compose — `http://helpdesk:8090` |
| `ldap`, профиль `ldap` (`emulators/ldap`) | каталог OpenLDAP с тремя пользователями | `ldap://ldap:389` со StartTLS, см. [authentication.md](authentication.md#тестовый-каталог-ldap) |

Эмулятор заявок написан на FastAPI и хранит заявки в JSON в томе `vena-helpdesk`. Вызовы: `POST /tickets`, `GET /tickets/{id}`, `GET /tickets?status=…`, `GET /equipment`. Статус заявки меняется со временем: принята через `HELPDESK_ACCEPT_SECONDS` (60 с), в работе — через `HELPDESK_START_SECONDS` (180 с), закрыта — через `HELPDESK_CLOSE_SECONDS` (600 с). Локальный backend подключён к эмулятору сразу (`VENA_HELPDESK_URL=http://helpdesk:8090`, токен `local-helpdesk-token`). Пустое значение `VENA_HELPDESK_URL=` отключает отправку заявок.

```bash
curl -H 'Authorization: Bearer local-helpdesk-token' http://localhost:8090/tickets
```

`GET /equipment` отдаёт 17 каналов из `emulators/helpdesk/fixtures/equipment.json` в формате коннектора учётной системы. Синхронизация с ним в compose выключена: каналы эмулятора попали бы в реестр и в справочник ML. Включайте её только на стенде без реального справочника: `VENA_EQUIPMENT_SYNC_ENABLED=true docker compose up -d backend`. Если канал уже загружен с другим `external_id`, синхронизация отклоняется целиком.

## LDAP / Active Directory (ТЗ 11)

Вход через корпоративный каталог включается в серверном `.env`. Пример для AD:

```dotenv
VENA_LDAP_ENABLED=true
VENA_LDAP_URL=ldaps://dc.example.local:636
VENA_LDAP_BIND_DN=CN=vena-reader,OU=Services,DC=example,DC=local
VENA_LDAP_BIND_PASSWORD=replace-on-server
VENA_LDAP_BASE_DN=OU=Users,DC=example,DC=local
VENA_LDAP_USER_FILTER=(|(sAMAccountName={login})(userPrincipalName={login})(mail={login}))
VENA_LDAP_GROUP_ROLES={"CN=Vena-Admins,OU=Groups,DC=example,DC=local":"admin","CN=Vena-Dispatchers,OU=Groups,DC=example,DC=local":"dispatcher"}
VENA_LDAP_DEFAULT_ROLE=none
VENA_LDAP_CA_FILE=/srv/certs/customer-ca.pem
```

Для OpenLDAP задайте `VENA_LDAP_USERNAME_ATTRIBUTE=uid`, `VENA_LDAP_ID_ATTRIBUTE=entryUUID` и включите overlay memberOf. `ldap://` всегда переходит на StartTLS до bind, `ldaps://` сразу работает по TLS; сертификат проверяется. Роль определяется по прямому членству в группах (берётся наибольшая), `DEFAULT_ROLE=none` запрещает вход без группы. После перезапуска backend `GET /api/v1/auth/status` возвращает `ldap_available=true`, а на экране входа появляется вход через каталог. Области видимости групп (`VENA_LDAP_GROUP_SCOPES`), сессии и тестовый каталог описаны в [authentication.md](authentication.md#области-видимости).

## Резервное копирование

Копии, проверка и восстановление описаны в [installation.md](installation.md#резервное-копирование) и [infra/README.md](../infra/README.md#резервные-копии).
