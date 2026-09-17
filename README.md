# VENA — ЛЦТ 2026, кейс №8 (АО «Москоллектор»)

Risk-скоринг отказа канала (насос / вентилятор / дым) по журналу событий. Baseline: CatBoost / LogisticRegression.

## Данные

| | |
|---|---|
| Период | 2019-01-01 … 2026-06-30 |
| Событий | 313 546 219 |
| Каналов с «Неисправен» | 4821 |
| Срабатываний литерала | 1 500 298 |
| Эпизодов отказа (после group 6ч) | 89 905 |
| Направления в модели | pump, fan, smoke |
| Газ | проверен, ROC AUC ≈ 0.51 — исключён |
| Температура | 83 эпизода за 8 лет — исключён |
| Реестр оборудования / история ремонтов / АРМ-Контроль / СКУД / визуальные осмотры | отсутствуют в данных |

## Анализ данных

Проверил рекурсивно всю директорию датасета (`find . -maxdepth 4`) — заявленных в ТЗ таблиц (реестр оборудования, журнал неисправностей, АРМ-Контроль, СКУД) физически нет, кроме уже перечисленных выше файлов.

**Схема.** Собрал каталог колонок по всем 8 годовым файлам (`analysis/02_schema_catalog.md`). Набор колонок одинаковый во всех годах (`ид_события`, `ид_канала_данных`, `дата`, `время`, `тревожное`, `значение_датчика`). `значение_датчика` — смешанный тип: число или один из ~34 повторяющихся текстовых литералов состояния (`Неисправен`, `Обесточен`, `Батарея разряжена` и т.д.). Демо-файл `журнал_событий_пример.csv` кодирует `тревожное` как `true`/`false` вместо `f`/`t` — привёл к единому виду перед объединением.

**Качество.** Нашёл и учёл:

| Проблема | Масштаб |
|---|---|
| Скрытые null (`"Неопределен"`, epoch-заглушка `01.01.1970`) | ~7.59 млн строк (2.4%) |
| Дубликаты `ид_события` внутри года | до 2.46% строк (2023) |
| Полные дубликаты строк | до 1.92% строк (2023) |
| Конфликтующие показания в одну секунду | до 2.42% строк (2023) |
| `ид_события` не уникален глобально | подтверждено ≥20 межгодовых коллизий |
| Каналы в событиях без записи в справочнике | 1142 из 12 627 (9.0%) |
| Склейка двух полугодий в `ext-journal-2025.csv` | дублирующийся заголовок на строке 26 140 585, вырезал |

Перед обучением делаю дедупликацию по `(ид_канала_данных, дата, время, значение_датчика, тревожное)`.

**Связи между таблицами.** Проверил гипотезу «код в `тег_инженерной_системы` = id из справочника объектов» — совпадения слабые и несистемные (максимум 16 из 570 уникальных значений на одной позиции токена), отклонил как случайную коллизию. Реальная связь в данных только одна: `EVENT → CHANNEL` (по `ид_канала_данных`), покрытие растёт с 88% событий в 2019 до 100% в 2025-2026. Цепочки `CHANNEL → SYSTEM → OBJECT → EQUIPMENT → INCIDENT → REPAIR` из ТЗ в данных нет — `справочник_объектов_диспетчер.csv` физически изолирован от событий.

**Аномалия 2021.** Апрель–июнь 2021: до 819 021 событий `"Неисправен"` за май на ~80–130 каналах — локализованный сбой мониторинга/связи, не волна физических поломок. После группировки в эпизоды окном 6ч аномалия сглаживается, распределение по годам становится ровным (4602 эпизода в 2019 → 15777 в 2025). Поэтому считаю target на уровне эпизода, а не тика.

**Разметка риска утечки.** Составил таблицу полей по риску (`analysis/08_leakage_and_validation.md`): скользящие статистики и `time_since_last_*` безопасны при строгом окне `(., t]`; сам литерал `"Неисправен"` в момент ≥t — утечка, если использовать как признак; склеенная строка-заголовок в 2025 — утечка/порча, вырезается до сплита.

**Почему не random split.** Данные — временной ряд по каналу, а не независимые наблюдения; справочник каналов дрейфует во времени (82%→100% покрытия); в данных есть локализованная аномалия (2021). Random split завысил бы метрики. Использую только temporal split по годам (см. Validation ниже).

**Feature engineering.** Из ТЗ-списка признаков вычислимо напрямую: частотные (`alarms_Nh`, `time_since_last_event/failure`, `event_rate_delta`, `burst_count`, interarrival stats), календарные (season/weekday/hour), метаданные канала (`тип_датчика`, `тип_инж_системы`). Не вычислимо и не использую: `sensor_age` (нет дат установки), `district`/геопривязка (нет координат), настоящий `false_alarm_ratio` (нет поля верификации), `time_since_last_repair` (нет журнала ремонтов). Погоду добавил как внешний признак (единая точка «Москва», без district-уровня) — не дала прироста, исключил (см. таблицу «Исключено»).

## Target

Новый эпизод `"Неисправен"` на канале в `(t, t+24h]` или `(t, t+72h]`. Признаки только `<= t`. Equipment Failure Risk — прокси по состоянию датчика, не физический износ и не RUL.

## Pipeline

```
events → candidates (alarm/fault_adjacent/recovery/burst/transition/silence)
       → episodes → causal features (10м…30д, EWMA, приоры, интервалы, календарь)
       → model → ranking (daily top-K) → alerts (cooldown dedup)
```

## Baseline

| Устройство | Горизонт | Модель |
|---|---|---|
| Насос | 24ч | CatBoost |
| Насос | 72ч | LogisticRegression |
| Вентилятор | 24ч | CatBoost |
| Вентилятор | 72ч | CatBoost |
| Дым | 24ч | CatBoost |

Конфиги: `configs/models/*.json`. Артефакты: `artifacts/models/*/{model.joblib,meta.json}`.

## Результаты (test = 2025–2026H1, out-of-time)

| Устройство | Горизонт | ROC AUC | avg_precision | daily top-1% | alert precision | episode recall | median lead time |
|---|---|---|---|---|---|---|---|
| Насос | 24ч | 0.623 | 0.273 | 44.3% | 23.6% | 4.9% | 14.0ч |
| Насос | 72ч | 0.666 | 0.448 | 70.8% | 50.6% | 8.2% | 52.8ч |
| Вентилятор | 24ч | 0.817 | 0.183 | 18.3% | 16.0% | 4.4% | 13.4ч |
| Вентилятор | 72ч | 0.858 | 0.411 | 38.2% | 35.0% | 7.7% | 46.8ч |
| Дым | 24ч | 0.917 | 0.225 | 13.2% | 13.2% | 24.8% | ≈5 мин |

Дым: recall выше всех, lead time ≈5 мин.

## Metrics glossary

| Метрика | Что это |
|---|---|
| daily top-1% | precision/recall на верхнем 1% risk_score по каждому дню отдельно |
| alert precision | daily top-K после cooldown-дедупликации по каналу (24/48/72ч) |

alert precision ≤ daily top-K precision всегда.

## Validation

| Fold | Train | Valid |
|---|---|---|
| 1 | ≤ 2021 | 2022 |
| 2 | ≤ 2022 | 2023 |
| 3 | ≤ 2023 | 2024 |
| 4 | ≤ 2024 | 2025 |

Model selection: rolling через 2025. Невиданный период: 2026H1.

## Formal 70/50 (Precision≥0.7 и Recall≥0.5 одновременно)

Не достигнуто ни для одной модели. Порог подбирается только на VALID.

| Устройство/горизонт | При precision≥0.7 | При recall≥0.5 |
|---|---|---|
| Насос 72ч | precision 0.747, recall 0.132 | recall 0.512, precision 0.369 |
| Вентилятор 72ч | — | recall 0.601, precision 0.348 |
| Дым 24ч | precision 0.809, recall 0.007 | recall 0.682, precision 0.124 |

## Исключено

| Что | Причина |
|---|---|
| Погода | не даёт устойчивого прироста ни на одном устройстве |
| Duty-cycle | ухудшает насос (0.215→0.202), нейтрально для вентилятора |
| XGBoost | стабильно хуже CatBoost/LogReg |
| Газ | ROC AUC ≈ 0.51 |
| Температура | 83 эпизода за 8 лет |

## Deep Temporal Models (`pipeline/sequence/`) — экспериментально, не production

Custom Event Transformer: d_model=128, 3 encoder layers, 4 heads, 614k параметров.

| Stage | Статус |
|---|---|
| A/B1 (scratch, Pump72, 4-fold) | хуже LogReg: daily_top1 0.463 vs 0.548 |
| B2 | max_len=128 зафиксирован |
| C-A (self-supervised pretrain) | не помогает |
| E (hybrid seq+tabular) | fold3 — победа над обоими baseline на 4/6 метрик; fold2/fold4 на момент снимка (2026-09-17) ещё считались |

Production-артефакты этот трек не использует и не меняет.

## Run

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.12. `dataset/` (~15ГБ) и `external_datasets/` (~1ГБ) — локально, не в git.

Один прогон:

```bash
python3 -m pipeline.run --sensor-type pump --horizon 24 --models catboost,logistic_regression
```

Все 5 конфигов → `results/baseline_metrics.csv`:

```bash
python3 run_baseline_suite.py
```

Оценка своих predictions:

```python
from pipeline import evaluate
metrics = evaluate.evaluate_predictions(
    channel_id, prediction_time, y_true, risk_score,
    episodes=episodes_df, horizon_hours=72, cooldown_hours=24,
)
```

Тесты:

```bash
python3 -m pytest -m "not slow"
```

## Структура

| Путь | Назначение |
|---|---|
| `pipeline/extract.py` | чтение и кэш сырых данных |
| `pipeline/episodes.py` | группировка эпизодов, target |
| `pipeline/candidates.py` | причинные кандидаты |
| `pipeline/features.py` | причинные признаки |
| `pipeline/tags.py` | разбор/группировка тегов каналов |
| `pipeline/weather.py` | погодные признаки (исключены) |
| `pipeline/splits.py` | temporal split |
| `pipeline/backtest.py` | rolling folds |
| `pipeline/models.py` | CatBoost/LogReg обёртки |
| `pipeline/training.py` | feature columns, прогон моделей |
| `pipeline/ranking.py` | ranker-модель (эксперимент) |
| `pipeline/calibration.py` | Platt/isotonic |
| `pipeline/decision.py` | подбор порога |
| `pipeline/evaluate.py` | метрики, `evaluate_predictions` |
| `pipeline/alerts.py` | cooldown, coverage |
| `pipeline/error_analysis.py` | разбор FN/near-miss |
| `pipeline/artifacts.py` | сохранение/загрузка моделей |
| `pipeline/inference.py` | сборка фич + скоринг в проде |
| `pipeline/experiments.py` | оркестрация серии экспериментов |
| `pipeline/config.py` | константы |
| `pipeline/run.py` | CLI entrypoint |
| `pipeline/sequence/` | transformer, эксперимент, не production |
| `pipeline/tests/` | тесты |
| `configs/models/` | frozen конфиги (5 combo) |
| `artifacts/models/` | frozen модели |
| `run_baseline_suite.py` | все 5 baseline конфигов → CSV |
| `run_final_freeze.py`, `run_final_sprint.py`, `run_experiment_battery.py`, `build_final_matrix.py` | эксперименты, пишут в `analysis/` |

`analysis/`, `dataset/`, `external_datasets/` — локально, в `.gitignore`.

## Дальше

- Прогоняю `run_baseline_suite.py` на полном датасете, фиксирую `results/baseline_metrics.csv`.
- Довожу isotonic-калибровку в `pipeline/inference.py`.
- Смотрю Stage E (fold2/fold4) по transformer, обновляю таблицу выше по завершении.
- Chronic-channel routing для pump/smoke — в работе.
