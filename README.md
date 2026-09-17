# VENA

Predictive maintenance pipeline for АО «Москоллектор» engineering utility collectors (ЛЦТ 2026, кейс №8). Predicts sensor failure / equipment-degradation risk (pump, fan, smoke) from raw event-log data and ranks channels by risk for preventive inspection.

## Что решает

- **Sensor Failure risk** — вероятность того, что канал перейдёт в состояние `"Неисправен"` в ближайшие 24 или 72 часа. Основное направление: у него есть буквальный, честный ground truth в данных.
- **Equipment Failure Risk / Operational Degradation** — тот же механизм (события → эпизоды → причинные признаки → модель) применён как **прокси** операционной деградации оборудования (насос, вентилятор). Это **не** физический износ (%), не RUL (remaining useful life) и не survival-модель — таких данных в датасете нет (см. ниже). Это оценка риска в терминах наблюдаемого состояния датчика, а не паспорта оборудования.

## Данные

- Журнал событий СМВУ 2019-01-01 … 2026-06-30: **313 546 219** строк (`dataset/ext-journal-2019.csv` … `ext-journal-2026.csv`).
- Справочник каналов датчиков (`справочник_каналов_датчиков.csv`), справочник объектов диспетчер (`справочник_объектов_диспетчер.csv`, малополезен — без дат ввода в эксплуатацию и без насосов/вентшахт/камер как физических активов).
- Ground truth «Неисправен»: 1 500 298 срабатываний литерала на 4821 канале → после группировки flapping-окном 6ч — **89 905 отдельных эпизодов отказа** за 8 лет.
- Основные направления: pump (`Состояние насоса`), fan (`Состояние вентилятора`), smoke (`Датчик дыма`).
- **Газовый датчик проверен и исключён**: полный pipeline прогнан (extract→candidates→features→3 модели), ROC AUC≈0.51 на test у всех моделей — неотличимо от случайного, несмотря на 71% всего объёма событий (224М из 313.5М, высокочастотная числовая телеметрия, а не событийный поток).
- **Температура исключена**: только 83 эпизода отказа за 8 лет на 600 каналах — недостаточно для обучения (avg_precision неотличим от случайного).
- **Чего в данных физически нет** (проверено рекурсивным сканированием всей директории датасета): реестра оборудования с датами ввода в эксплуатацию и историей ремонтов, журнала неисправностей/заявок, АРМ-Контроль, СКУД, истории визуальных обследований. Это жёстко ограничивает любую честную постановку «износа инфраструктуры» — полноценный survival/RUL-подход не поддержан данными.

## Target

Новый эпизод `"Неисправен"` на канале в окне `(t, t+24h]` или `(t, t+72h]`, где `t` — момент кандидата (prediction_time). В признаках используется только информация `<= t` (причинно, без утечки будущего — см. ниже). Формулируется как **Equipment Failure Risk / Operational Degradation proxy**, явно не как физический износ или remaining-useful-life: датчик отражает наблюдаемое состояние, не возраст/паспорт оборудования.

## Pipeline

`events → candidates (причинные триггеры: alarm, fault_adjacent, recovery, burst, transition, silence) → episodes (группировка отказов) → causal features (окна 10м…30д, EWMA, приоры по каналу, inter-failure интервалы, календарные) → model → ranking (daily top-K) → alerts (cooldown-дедупликация)`.

Причинность candidate generation проверена явно: burst-триггер использует **expanding** (расширяющееся, только по истории до текущей точки, со сдвигом `shift(1)`) вычисление квантиля межсобытийных интервалов (`pipeline/candidates.py::_burst_mask`), а не lookback-окно, заглядывающее в будущее — исторический баг такого рода исправлен и покрыт тестами (`pipeline/tests/test_pipeline.py`).

## Baseline-модели

| Устройство | Горизонт | Модель | Почему |
|---|---|---|---|
| Насос | 24ч | CatBoost | лучший daily top-1% (0.443) и end-to-end alert-precision на коротком горизонте, подтверждено rolling backtest (4 folds) |
| Насос | 72ч | LogisticRegression | стабильно обходит CatBoost по всем метрикам rolling backtest на 72ч |
| Вентилятор | 24ч | CatBoost | побеждает LogReg на обоих горизонтах в rolling backtest и в ensemble-проверке |
| Вентилятор | 72ч | CatBoost | — |
| Дым | 24ч | CatBoost | выигрывает у LogReg более чем вдвое по avg_precision (0.184 vs 0.082) |

Конфиги — `configs/models/*.json`, артефакты — `artifacts/models/*/{model.joblib,meta.json}`.

## Результаты (test = 2025–2026H1, out-of-time)

| Устройство | Горизонт | ROC AUC | avg_precision | daily top-1% | alert precision (cooldown 24ч) | episode recall | median lead time |
|---|---|---|---|---|---|---|---|
| Насос | 24ч | 0.623 | 0.273 | 44.3% | 23.6% | 4.9% | 14.0ч |
| Насос | 72ч | 0.666 | 0.448 | 70.8% | 50.6% | 8.2% | 52.8ч |
| Вентилятор | 24ч | 0.817 | 0.183 | 18.3% | 16.0% | 4.4% | 13.4ч |
| Вентилятор | 72ч | 0.858 | 0.411 | 38.2% | 35.0% | 7.7% | 46.8ч |
| Дым | 24ч | 0.917 | 0.225 | 13.2% | 13.2% | 24.8% | **≈0.08ч (~5 мин)** |

Эти числа прочитаны из `artifacts/models/*/meta.json::metrics_snapshot` и перепроверены в этой сессии — совпадают с `analysis/tables/final_model_matrix.csv` и `analysis/STATUS.md`. Полная перетренировка на всех 313М событий в рамках этой сессии не запускалась (см. раздел «Run» — это дорогостоящая операция); reproducibility проверена через провенанс сохранённых артефактов/снапшотов, произведённых тем же кодом (`run_final_freeze.py` → `pipeline/evaluate.py`, `pipeline/alerts.py`), который доступен для повторного запуска.

**Важная оговорка по дыму**: end-to-end recall у дыма (24.8%) самый высокий среди всех устройств, но median lead time ≈5 минут — большинство алертов срабатывают почти одновременно с отказом, а не заранее, что почти бесполезно для превентивного осмотра. Насос 72ч даёт lead time 52.8ч при втрое меньшем recall — это продуктовый компромисс, не технический вывод.

## Metrics glossary

- **daily top-1%** — для каждого дня отдельно берутся кандидаты с наивысшим risk_score (верхний 1% по этому дню); precision/recall считаются на этой отобранной по дням выборке. Метрика ранжирования продукта («какая доля дневного топа реально отказала»).
- **alert precision (после cooldown)** — из daily top-K дополнительно применяется дедупликация: повторный алерт по тому же каналу подавляется в течение cooldown-окна (24/48/72ч). Метрика ближе к «что реально увидит дежурный», а не сырая точность классификатора.
- Это **разные** величины: alert precision всегда ≤ daily top-K precision на той же выборке (дедупликация убирает часть верных совпадений). При сравнении с внешней моделью (Ilya) сверяйте, какая именно метрика на какой стадии пайплайна посчитана — не сравнивайте raw classification precision с alert precision напрямую.

## Validation

Rolling temporal folds: `train ≤ 2021 → valid = 2022`, `train ≤ 2022 → valid = 2023`, `train ≤ 2023 → valid = 2024`, `train ≤ 2024 → valid = 2025`. Модель/фичи/гиперпараметры отбирались только по этим 4 folds. **2025 год участвует и в model selection (fold 4 valid), и частично в финальном out-of-time окне** — честная формулировка: model selection идёт rolling через 2025, а по-настоящему невиданный период — **2026H1**. Заявление «весь 2025–2026H1 не тронут при подборе» было бы неточным и не используется здесь.

## Formal 70/50 (Precision≥0.7 И Recall≥0.5 одновременно)

**Не достигается ни для одного устройства/горизонта** — подтверждено кодом threshold sweep (`pipeline/decision.py::freeze_threshold_max_recall_at_precision` / `freeze_threshold_max_precision_at_recall`, порог выбирается **только на VALID**, затем применяется на TEST без переподбора — проверено тестом на неизменность порога).

По отдельности, out-of-sample:
- Насос 72ч: precision≥0.7 → precision=0.747, recall=0.132; recall≥0.5 → recall=0.512, precision=0.369.
- Вентилятор 72ч: recall≥0.5 → recall=0.601, precision=0.348.
- Дым 24ч: precision≥0.7 → precision=0.809, recall=0.007 (практически бесполезно); recall≥0.5 → recall=0.682, precision=0.124.

## Deep Temporal Models (экспериментальный трек — НЕ production)

`pipeline/sequence/` — отдельная активная исследовательская ветка (custom Event Transformer: `d_model=128`, 3 encoder layers, 4 heads, 614 017 параметров, per-event представление state/alarm/delta-time/time-of-day). Production-модели/конфиги/артефакты (`configs/models/`, `artifacts/models/`) не затронуты и не используются этим треком.

Статус по данным `analysis/ML_EXPERIMENTS.md`, `analysis/STATUS.md` (снимок на 2026-09-17, трек продолжает выполняться конкурентно — **не проверено вживую в рамках этой сессии**, могло уйти дальше):
- Stage A/B1 (scratch, Pump72, 4-fold): transformer хуже LogReg по alert_precision/episode_recall на всех 4 фолдах (mean daily_top1 0.463 vs 0.548 у LogReg).
- Stage B2: `max_len=128` зафиксирован (лучше `256` по всем средним метрикам).
- Stage C-A (self-supervised pretraining на своих данных): не помогает, хуже scratch на 2 проверенных фолдах — не масштабировано на оставшиеся.
- Stage E (hybrid: sequence + причинные табличные признаки): fold1 — смешанный результат, fold3 — устойчивая победа над обоими бейзлайнами (scratch transformer и frozen LogReg) на 4 из 6 метрик; fold2/fold4 были в процессе выполнения на момент последнего чтения статуса. Итоговый вердикт по Stage E не вынесен.

Это исследование не блокирует и не заменяет baseline-пайплайн, описанный выше.

## Исключённые признаки/модели (по документированным экспериментам)

- **Погода (Open-Meteo)** — проверена на всех 3 устройствах, везде либо вредит, либо нейтральна.
- **Duty-cycle признаки** — вредят насосу (avg_precision 0.215→0.202), нейтральны для вентилятора.
- **XGBoost** — стабильно худший из 4 моделей на насосе и вентиляторе.
- **Газовый датчик** — ROC AUC≈0.51, направление закрыто.
- **Температура** — слишком мало эпизодов отказа (83 за 8 лет), направление закрыто.

## Run

### Установка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Python 3.12. Сырой датасет (`dataset/`, ~15ГБ) и внешние датасеты (`external_datasets/`, ~1ГБ) не хранятся в git — ожидаются локально по путям выше (см. `.gitignore`).

### Воспроизведение baseline

Один train/eval прогон:

```bash
python3 -m pipeline.run --sensor-type pump --horizon 24 --models catboost,logistic_regression
```

Все 5 финальных конфигов одной командой (переиспользует `run_final_freeze.run_final_for_device`, пишет `results/baseline_metrics.csv`):

```bash
python3 run_baseline_suite.py
```

Полный экспериментальный батч и заморозка отдельных моделей — `run_experiment_battery.py`, `run_final_sprint.py`, `run_final_freeze.py <device> <horizon> <model>`, `build_final_matrix.py` (пишут в `analysis/tables/`, задокументированы в `analysis/ML_EXPERIMENTS.md`/`analysis/STATUS.md`).

### Оценка своей модели (apples-to-apples)

Единая точка входа — `pipeline.evaluate.evaluate_predictions`:

```python
from pipeline import evaluate

metrics = evaluate.evaluate_predictions(
    channel_id, prediction_time, y_true, risk_score,
    episodes=episodes_df,      # опционально: для alert_precision / episode_recall / lead time
    horizon_hours=72,
    cooldown_hours=24,
)
```

Возвращает `roc_auc`, `avg_precision`, `precision_at_recall_0.5`, `recall_at_precision_0.7`, `daily top-K` (precision/recall для 0.1/0.5/1/2/5%), и при переданных `episodes`/`horizon_hours` — `alert_precision`, `end_to_end_recall` (episode recall), `median_lead_time_hours` после cooldown-дедупликации.

### Тесты

```bash
python3 -m pytest -m "not slow"
```

Полный прогон (включая end-to-end тест на реальном датасете):

```bash
python3 -m pytest
```

## Repository structure

```
pipeline/                  # ML pipeline package (baseline)
  run.py                   # CLI: single train/eval run
  candidates.py, episodes.py, features.py, splits.py
  models.py, training.py, evaluate.py, alerts.py, backtest.py
  decision.py, calibration.py, artifacts.py, inference.py
  experiments.py, error_analysis.py, ranking.py, tags.py, weather.py, extract.py, config.py
  sequence/                # experimental transformer track — not production
  tests/
configs/models/             # frozen inference configs (5 device/horizon combos)
artifacts/models/           # frozen model artifacts (model.joblib + meta.json)
run_final_freeze.py, run_final_sprint.py, run_experiment_battery.py, build_final_matrix.py
run_baseline_suite.py       # reproduces all 5 baseline configs -> results/baseline_metrics.csv
requirements.txt, pytest.ini, README.md
```

`analysis/` (data audits, experiment logs, tables/plots) and raw/external datasets stay local — see `.gitignore`.
