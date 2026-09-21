# VENA

ML-компонент предиктивного обслуживания инженерных систем (кейс №8, АО «Москоллектор», ЛЦТ 2026): по журналу событий датчиков оценивает риск наступления состояния оборудования в заданном горизонте и ранжирует каналы для осмотра.

## Problem

Журнал событий содержит состояния каналов (насосы, вентиляторы, датчики дыма/газа/температуры, фазы питания, ИБП, охрана и др.). Задача — по истории канала до момента `t` оценить вероятность того, что в интервале `(t, t+h]` начнётся целевой эпизод (например, «Неисправен» или «Обесточен»), и выдать ранжированный список кандидатов.

## Supported directions

| Направление | Target | Статус |
|---|---|---|
| Sensor Health | эпизод «Неисправен» датчика (дым 24ч) | замороженная модель в `artifacts/models` |
| Equipment Health | эпизод «Неисправен» насоса и вентилятора (24ч, 72ч) | замороженные модели в `artifacts/models` |
| Power Health | onset «Обесточен» у «Состояние фазы» (24ч; любой и устойчивый ≥30 мин) | модуль `pipeline.targets`, кандидат в production |
| Alarm Intelligence | подтверждение detection-alarm (дым, газ, температура) поведением системы за 15/30/60 мин | модуль `pipeline.targets`, shadow-режим |
| Incident Risk Proxies | Fire/Smoke Risk Index, Hydraulic Load Anomaly | только proxy-индексы (`pipeline.targets.proxies`), не вероятности инцидентов |
| Maintenance Priority | взвешенная композиция сигналов | решающее правило (`pipeline.targets.priority`), не обучаемый target |

Alarm Intelligence предсказывает подтверждение тревоги системным поведением, а не «ложную тревогу»: операторской метки истинной/ложной тревоги в данных нет. Реальных меток пожара и подтопления в данных нет, поэтому supervised-модели для них не обучаются.

## Data

Данные не входят в репозиторий (проприетарные). Ожидаемая структура:

```
dataset/
  ext-journal-2019.csv ... ext-journal-2026.csv
  справочник_каналов_датчиков.csv
```

Журнал: период 2019-01-01 … 2026-06-30, ≈313.5 млн событий, 19 типов датчиков. Единственная связь между таблицами — `EVENT → CHANNEL` по `ид_канала_данных`. Корень проекта переопределяется переменной окружения `LCT_PROJECT_ROOT`. Кэш извлечённых событий пишется в `analysis/ml_ready/cache` (в git не попадает).

## Targets

- Эпизод состояния — события одного канала с одним значением, сгруппированные окном 6 часов; начало эпизода — первое событие группы.
- Метка кандидата в момент `t`: начало целевого эпизода в `(t, t+h]`. Горизонты: 24ч и 72ч для отказов, 24ч для питания, 15/30/60 мин для подтверждения тревог.
- Устойчивое отключение: onset «Обесточен», после которого канал остаётся в этом состоянии ≥30 минут.
- Подтверждение тревоги: повтор alarm на том же канале, alarm другого канала той же tag-группы или detection-состояние длительностью ≥W минут.
- Признаки используются только по событиям `≤ t`; периоды, попадающие в закрытый период 2026H1, исключены из загрузчиков исследовательских данных.

## Architecture

```
events → candidate generation → causal features → model → risk score → ranking / alerts (cooldown) → API / product
```

- `pipeline/extract.py`, `episodes.py`, `candidates.py`, `features.py` — извлечение, эпизоды, кандидаты, causal-признаки.
- `pipeline/models.py`, `training.py`, `backtest.py`, `evaluate.py`, `alerts.py`, `decision.py`, `calibration.py` — модели, rolling backtest, метрики, алерты, пороги.
- `pipeline/artifacts.py`, `inference.py` — сохранение и инференс замороженных моделей.
- `pipeline/targets/` — новые направления: target discovery, generic state-target, Power Health, Alarm Corroboration, proxy-индексы, приоритет.
- `pipeline/formal/` — инструменты для формальной цели Precision ≥ 0.70 и Recall ≥ 0.50 (PR-frontier, перенос порога, hard-negative веса, lockbox-guard).
- `pipeline/sequence/` — экспериментальные последовательные модели (transformer, hybrid); research-only, production baseline не заменяют.

## Models

| Направление | Модель | Где |
|---|---|---|
| Pump 24ч | CatBoost | `artifacts/models/pump_24h` |
| Pump 72ч | LogisticRegression | `artifacts/models/pump_72h` |
| Fan 24ч, 72ч | CatBoost | `artifacts/models/fan_24h`, `fan_72h` |
| Smoke 24ч | CatBoost | `artifacts/models/smoke_24h` |
| Power Health | LightGBM | `python -m pipeline.targets.run phase` |
| Alarm Corroboration | LightGBM | `python -m pipeline.targets.run alarm` |

Конфиги инференса замороженных моделей — `configs/models/*.json`. Артефакты компактные (до ≈350 КБ каждый) и нужны для запуска инференса.

## Validation

Только строгая временная валидация, без random split: rolling backtest из 4 фолдов (train до года N, valid — год N+1: 2022, 2023, 2024, 2025). Пороги выбираются на предыдущем периоде и применяются без пересчёта. Период 2026H1 зарезервирован как закрытый (lockbox) и не участвует в выборе моделей и признаков.

## Metrics

Метрики считаются на уровне кандидатов (precision, recall, PR-AUC, ROC AUC, recall при precision 0.70, precision при recall 0.50) и операционные: daily top-1%, alert precision (дедупликация cooldown), episode recall, lead time, candidate coverage.

| Направление | Результат (rolling folds 2022–2025) |
|---|---|
| Pump 72ч (LogReg) | AP 0.405; вариант с hard-negative весами (исследовательский) — AP 0.425; formal 70/50 **не достигнут** (на валидации 2025 P=0.70 достигается только при R=0.21) |
| Fan 72ч (CatBoost) | AP 0.338; formal 70/50 **не достигнут**; blend CatBoost+hybrid улучшает только operational ranking |
| Power Health, onset за 24ч (LightGBM) | AP 0.87, ROC AUC 0.92; на всех фолдах существует порог с P ≥ 0.70 и R ≥ 0.50; при пороге предыдущего фолда: alert precision 0.66, episode recall 0.75 |
| Power Health, устойчивое отключение за 24ч (LightGBM) | AP 0.93, ROC AUC 0.96 |
| Alarm Corroboration, 30 мин (LightGBM / CatBoost) | ROC AUC 0.89, PR-AUC 0.96 |

Формальная цель Precision ≥ 0.70 и Recall ≥ 0.50 для отказов Pump72/Fan72 **не достигнута**; для Pump72 на закрытом периоде 2026H1 при замороженном пороге: P=0.51, R=0.25.

## Reproduction

```bash
python -m pipeline.run --sensor-type "Состояние насоса" --horizon 72 --models logistic_regression,catboost --out results/pump_72h.csv
python run_final_freeze.py pump 72 logistic_regression
python run_baseline_suite.py
python -m pipeline.targets.run discovery
python -m pipeline.targets.run phase --target any --horizon 24 --train-end 2024 --valid-year 2025
python -m pipeline.targets.run alarm --window 30 --train-end 2024 --valid-year 2025
```

Команды `phase` и `alarm` пишут модель и отчёт в `artifacts/experimental` (в git не попадает).

## Project structure

```
pipeline/            основной код (данные, признаки, модели, метрики)
  targets/           направления: discovery, Power Health, Alarm Corroboration, proxy, приоритет
  formal/            формальная цель Precision/Recall, lockbox-guard
  sequence/          research-only последовательные модели
  tests/             тесты
configs/models/      конфиги инференса замороженных моделей
artifacts/models/    замороженные модели
run_final_freeze.py, run_baseline_suite.py   воспроизведение замороженных моделей и baseline
```

## Tests

```bash
python -m pytest
```

100 тестов, все проходят (≈75 с).

## Installation

Python 3.12, зависимости в `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Limitations

В данных отсутствуют: подтверждение оператором истинности тревог, возраст оборудования, история ремонтов, геопривязка, данные АРМ-Контроль и СКУД. Поэтому «вероятность отказа» — оценка риска состояния датчика по журналу, а не физический износ и не остаточный ресурс; proxy-индексы не являются вероятностями пожара или подтопления. Более половины эпизодов отказа — одиночные события нулевой длительности, что ограничивает достижимое качество.
