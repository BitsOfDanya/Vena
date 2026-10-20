# Библиотеки и компоненты

Версии — из `backend/pyproject.toml`, `ml/requirements.txt`, `frontend/package.json`, Dockerfile и compose; точные — в `backend/uv.lock`
и `frontend/pnpm-lock.yaml`. ML-контейнер ставит `infra/docker/ml-requirements.txt`: без PyTorch, numba и pytest, но с закреплённым SciPy.

## Инфраструктура

| Компонент | Образ или версия | Назначение |
|---|---|---|
| PostgreSQL | `postgres:16-alpine` | оперативные данные, история, очередь писем |
| Python | `python:3.12-slim` | backend (зависимости через uv 0.11.19), ML-воркер, эмулятор заявок (FastAPI 0.141.1, uvicorn 0.53.0) |
| Node.js | `node:22-alpine`, pnpm 10.9.0 | сборка и сервер интерфейса |
| Caddy | `caddy:2-alpine` | HTTPS с автоматическим сертификатом, маршрутизация (стенд) |
| OpenLDAP | `osixia/openldap:1.5.0` | тестовый каталог, профиль `ldap` корневого compose |

## Backend

| Библиотека | Версия | Назначение |
|---|---|---|
| FastAPI `[standard-no-fastapi-cloud-cli]`, pydantic-settings | ≥0.141.1, ≥2.15.0 | REST API, OpenAPI, uvicorn; конфигурация из окружения |
| SQLAlchemy, Alembic, psycopg `[binary]` | ≥2.0.54, ≥1.20.0, ≥3.2.0 | ORM, миграции, драйвер PostgreSQL |
| APScheduler | ≥3.11.0 | фоновые задания: приём снимка, очередь писем, публикация загрузок, синхронизации, сводка |
| PyJWT, pwdlib `[argon2]`, ldap3 | ≥2.10 <3, ≥0.3 <1, ≥2.9.1 <3 | JWT, хеши паролей Argon2, вход через LDAP/AD |
| httpx | ≥0.28 <1 | обмен с учётной системой и системой заявок |
| openpyxl, ReportLab, defusedxml, python-multipart | ≥3.1, ≥4.4 <5, ≥0.7 <1, ≥0.0.20 | XLSX, PDF, безопасный разбор XML, загрузка файлов |
| email-validator; smtplib (stdlib) | ≥2.2.0 | проверка адресов; отправка писем |
| pytest, mypy, ruff (dev) | ≥9.1.1, ≥2.3.1, ≥0.16.8 | тесты, типизация, линтер |

## ML

| Библиотека | Версия | Назначение |
|---|---|---|
| pandas, numpy | 2.2.1, 1.26.4 | обработка событий и признаков |
| DuckDB, pyarrow | 1.5.5, 18.1.0 | чтение журналов CSV, кэш событий в Parquet |
| scikit-learn | 1.5.1 | логистическая регрессия, изотоническая калибровка, метрики |
| LightGBM | 4.7.0 | насосы (смесь с логистической регрессией), подтопление, подтверждение тревог, модели объекта, срок до отказа |
| CatBoost | 1.2.5 | вентиляторы, дымовые датчики, потеря питания |
| SciPy, joblib | 1.13.1, 1.3.2 | сглаживание кривой индекса здоровья; сериализация моделей |
| requests | 2.32.3 | загрузка метеоданных Open-Meteo |
| XGBoost, PyTorch, numba, pytest | 2.0.3, 2.2.1, 0.67.0, 8.0.0 | исследовательские сравнения и последовательные модели, ускорение признаков, тесты |

## Frontend

| Библиотека | Версия | Назначение |
|---|---|---|
| Next.js, React, React DOM | 16.3.5, 19.2.8 | App Router, сборка в standalone-сервер, UI |
| @tanstack/react-query, zod | ^5.103.1, ^4.6.5 | загрузка и кэширование данных API, валидация ответов |
| Tailwind CSS, tw-animate-css | ^4, ^1.4.0 | стили на семантических токенах |
| radix-ui, shadcn, class-variance-authority | ^1.6.7, ^4.21.0, ^0.7.1 | доступные примитивы интерфейса |
| react-hook-form, @hookform/resolvers | ^7.88.0, ^5.9.1 | формы |
| lucide-react, cmdk, sonner, next-themes | ^1.46.0, ^1.1.1, ^2.0.8, ^0.4.6 | иконки, командная палитра, всплывающие сообщения, тема |
| TypeScript, ESLint, Vitest (dev) | ^5, ^9, ^5.0.1 | типизация, линтер, тесты |

Графики, схема объекта и карта — собственные SVG-компоненты, сторонних библиотек визуализации нет.

## Внешние данные

Журнал СМВУ и справочники (CSV) используются для обучения и расчёта и в репозиторий не входят. Open-Meteo
(открытый API без ключа): архив погоды для проверки связи подтоплений с осадками и прогноз на 7 дней на дашборде
(`/api/v1/analytics/weather`). Открытый датасет MetroPT-3 — внешняя проверка метода (`ml/validate_external.py`).
