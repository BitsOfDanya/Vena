# VENA

ML-компонент предиктивного обслуживания инженерных систем (кейс №8, АО «Москоллектор», ЛЦТ 2026): по журналу событий датчиков оценивает риск наступления состояния оборудования в заданном горизонте и ранжирует каналы для осмотра.

## Problem

Журнал событий содержит состояния каналов (насосы, вентиляторы, датчики дыма/газа/температуры, фазы питания, ИБП, охрана и др.). Задача — по истории канала до момента `t` оценить вероятность того, что в интервале `(t, t+h]` начнётся целевой эпизод (например, «Неисправен» или «Обесточен»), и выдать ранжированный список кандидатов.

## Supported directions

| Направление | Target | Статус |
|---|---|---|
| Sensor Health | эпизод «Неисправен» датчика (дым 24ч) | замороженная модель в `artifacts/models` |
| Equipment Health | эпизод «Неисправен» насоса и вентилятора (24ч, 72ч) | замороженные модели в `artifacts/models` |
| Power Health | onset «Обесточен» у «Состояние фазы» (24ч; любой и устойчивый ≥30 мин) | замороженная модель `artifacts/models/phase_24h` |
| Alarm Intelligence | подтверждение detection-alarm (дым, газ, температура) поведением системы за 15/30/60 мин | модуль `pipeline.targets`, shadow-режим |
| Incident Risk Proxies | Fire/Smoke Risk Index, Hydraulic Load Anomaly | только proxy-индексы (`pipeline.targets.proxies`), не вероятности инцидентов |
| Maintenance Priority | взвешенная композиция сигналов | решающее правило (`pipeline.targets.priority`), не обучаемый target |

Alarm Intelligence предсказывает подтверждение тревоги системным поведением, а не «ложную тревогу»: операторской метки истинной/ложной тревоги в данных нет. Реальных меток пожара и подтопления в данных нет, поэтому supervised-модели для них не обучаются.

## Data

Данные не входят в репозиторий (проприетарные). Ожидаемая структура (относительно `ml/`):

```
dataset/
  ext-journal-2019.csv ... ext-journal-2026.csv
  справочник_каналов_датчиков.csv
```

Журнал: период 2019-01-01 … 2026-06-30, ≈313.5 млн событий, 19 типов датчиков. Единственная связь между таблицами — `EVENT → CHANNEL` по `ид_канала_данных`. Корень проекта переопределяется переменной окружения `LCT_PROJECT_ROOT`. Файлы журнала кладутся в `ml/dataset/`. Кэш извлечённых событий пишется в `ml/analysis/ml_ready/cache` (в git не попадает); результаты экспериментов лежат в `ml/results/`.

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
- `pipeline/formal/` — инструменты для формальной цели Precision > 0.70 и Recall > 0.50 (PR-frontier, перенос порога, hard-negative веса, lockbox-guard).
- `pipeline/sequence/` — экспериментальные последовательные модели (transformer, hybrid); research-only, production baseline не заменяют.

## Models

| Направление | Модель | Где |
|---|---|---|
| Pump 24ч | CatBoost | `artifacts/models/pump_24h` |
| Pump 72ч | смесь LogisticRegression + LightGBM 50/50, окно 3 года | `artifacts/models/pump_72h` |
| Pump 72ч, fallback для каналов с историей < 30 сут | LogisticRegression | `artifacts/models/pump_baseline_72h` |
| Fan 24ч, 72ч | CatBoost | `artifacts/models/fan_24h`, `fan_72h` |
| Smoke 24ч | CatBoost | `artifacts/models/smoke_24h` |
| Power Health 24ч | LightGBM | `artifacts/models/phase_24h` |
| Alarm Corroboration | LightGBM | `python -m pipeline.targets.run alarm` |

Конфиги инференса замороженных моделей — `configs/models/*.json`. Артефакты компактные (до ≈350 КБ каждый) и нужны для запуска инференса.

Все артефакты переобучены 28.09.2026 скриптом `run_production_refresh.py` после исправления признака `channel_failure_prior` и порядка событий. Метрики на тесте 2025 — 2026H1 (питание — на проверке 2025):

| Модель | AP | ROC AUC | Recall при P ≥ 0,70 | Precision при R ≥ 0,50 |
|---|---|---|---|---|
| `pump_24h` | 0.262 | 0.635 | 0.034 | 0.164 |
| `pump_72h` | 0.460 | 0.669 | 0.186 | 0.376 |
| `fan_24h` | 0.174 | 0.810 | 0.000 | 0.144 |
| `fan_72h` | 0.421 | 0.859 | 0.037 | 0.383 |
| `smoke_24h` | 0.227 | 0.915 | 0.025 | 0.202 |
| `phase_24h` | 0.871 | 0.918 | 0.813 | 0.987 |

## Prediction snapshot

`python score_snapshot.py` загружает замороженные артефакты, считает признаки по кэшу событий и пишет `results/predictions/snapshot.json` для API. Переобучения нет: используются только артефакты из `artifacts/models`.

Каждый канал оценивается в момент своего последнего события, а не в общую фиксированную секунду: модели обучены на моментах-кандидатах, и оценка «тихого» канала в произвольный момент выводит признаки за пределы обучающего распределения.

Уровни риска берутся из `risk_level_thresholds` конфига. У всех моделей `calibrated=false`, поэтому API отдаёт `score_type=risk_score`, а полосы — это операционные границы, а не вероятности. Основание полос различается по направлениям и указано в конфиге:

| Модели | Основание полос | Причина |
|---|---|---|
| `pump_*`, `fan_*`, `smoke_24h` | квантили 0.1% / 0.5% / 2% скорингового распределения | редкие события, хвост распределения совпадает с операционным интересом |
| `phase_24h` | пороги по измеренному precision 0.90 / 0.70 / 0.50 (`risk_level_basis`) | base rate 29%: квантиль топ-2% даёт порог 0.996 при операционной точке P=0.70 на 0.466, то есть полосы никогда не срабатывают |

## External validation

`python validate_external.py` прогоняет генератор кандидатов и признаки на MetroPT-3 (воздушный компрессор метро, 4 подтверждённых отказа из отчёта эксплуатации). Результат отрицательный и зафиксирован в `results/external/metropt3_validation.json`: ROC AUC 0.37, PR AUC 0.017, ни один предотказный интервал не попал в верхний 1% скоринга.

Причины: два отказа в обучающем периоде против десятков тысяч эпизодов в данных Москоллектора, и сигнатура утечки в MetroPT живёт в аналоговых величинах, тогда как признаки описывают динамику дискретных событий. Подбор порогов под четыре известных отказа не проводился — это была бы подгонка под ответ. Вывод о границах применимости: подход требует большого числа размеченных эпизодов и сигнатуры отказа в дискретных событиях или тревогах.

## Validation

Только строгая временная валидация, без random split: rolling backtest из 4 фолдов (train до года N, valid — год N+1: 2022, 2023, 2024, 2025). Пороги выбираются на предыдущем периоде и применяются без пересчёта. Период 2026H1 зарезервирован как закрытый (lockbox) и не участвует в выборе моделей и признаков.

## Metrics

Метрики считаются на уровне кандидатов (precision, recall, PR-AUC, ROC AUC, recall при precision 0.70, precision при recall 0.50) и операционные: daily top-1%, alert precision (дедупликация cooldown), episode recall, lead time, candidate coverage.

| Направление | Результат (rolling folds 2022–2025) |
|---|---|
| Pump 72ч (LogReg) | AP 0.405; вариант с hard-negative весами (исследовательский) — AP 0.425; formal 70/50 **не достигнут** (на валидации 2025 P=0.70 достигается только при R=0.21) |
| Fan 72ч (CatBoost) | AP 0.338; formal 70/50 **не достигнут**; blend CatBoost+hybrid улучшает только operational ranking |
| Power Health, onset за 24ч (LightGBM, `phase_24h`) | train ≤2024, валидация 2025: AP 0.87, ROC AUC 0.92, recall@P0.70 = 0.82, precision@R0.50 = 0.99; на операционной точке P=0.70 — alert precision 0.66, episode recall 0.75, медианный запас 5.9 ч, 181 алерт в сутки на 957 каналов |
| Power Health, устойчивое отключение за 24ч (LightGBM) | AP 0.93, ROC AUC 0.96 |
| Alarm Corroboration, 30 мин (LightGBM / CatBoost) | ROC AUC 0.89, PR-AUC 0.96 |

Формальная цель Precision > 0.70 и Recall > 0.50 для отказов Pump72/Fan72 **не достигнута**; исторические результаты замороженных production-моделей приведены выше.

Для Pump72 в production используется смесь логистической регрессии и LightGBM с окном обучения 3 года, найденная в [исследовании метрик](experiments/metric-improvement-2026-09-24.md) (`run_pump_blend_freeze.py`): на тесте она превосходит логистическую регрессию (AP 0.460 против 0.448), формальная цель остаётся недостигнутой. [Продолжение проверки метрик и исправление признака вентилятора](experiments/metric-improvement-followup-2026-09-24.md).

## Reproduction

Все команды выполняются из каталога `ml/`.

```bash
python -m pipeline.run --sensor-type "Состояние насоса" --horizon 72 --models logistic_regression,catboost --out out/pump_72h.csv
python run_final_freeze.py pump 72 logistic_regression
python run_baseline_suite.py
python -m pipeline.targets.run discovery
python -m pipeline.targets.run phase --target any --horizon 24 --train-end 2024 --valid-year 2025
python -m pipeline.targets.run alarm --window 30 --train-end 2024 --valid-year 2025
```

Результаты экспериментов (`results/`): `tables/` — baseline, rolling backtest, target discovery; `formal_70_50/` — исследование формальной цели Precision/Recall; `new_directions/` — Power Health, Alarm Corroboration, EBM/HMM/PWP, стеккинг и blend.

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
results/             таблицы результатов экспериментов и directions.json (для API)
run_production_refresh.py                     переобучение всех production-моделей и снимок прогнозов
run_final_freeze.py, run_pump_blend_freeze.py, run_power_freeze.py   заморозка отдельных моделей
score_snapshot.py                             снимок прогнозов для API
validate_external.py                          проверка на MetroPT-3
experiments/                                  исследования метрик Pump72/Fan72: скрипты и агрегированные результаты
run_baseline_suite.py                         baseline
```

## Tests

```bash
cd ml && python -m pytest
```

108 тестов, все проходят (≈80 с). `pipeline/tests` запускается раньше `experiments/` (см. `pytest.ini`).

## Installation

Python 3.12, зависимости в `requirements.txt`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Limitations

В данных отсутствуют: подтверждение оператором истинности тревог, возраст оборудования, история ремонтов, геопривязка, данные АРМ-Контроль и СКУД. Поэтому «вероятность отказа» — оценка риска состояния датчика по журналу, а не физический износ и не остаточный ресурс; proxy-индексы не являются вероятностями пожара или подтопления. Более половины эпизодов отказа — одиночные события нулевой длительности, что ограничивает достижимое качество.
