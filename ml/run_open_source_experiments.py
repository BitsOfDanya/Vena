"""Explore suitability of downloaded public datasets with fixed, separate tasks."""

import argparse
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from open_sources import experiments
from open_sources.download import SOURCES, digest
from run_independent_validation import run_external
from validation.evaluation import model_manifest

ROOT = Path(__file__).resolve().parent


def json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write_json(path, value):
    path.write_text(
        json.dumps(
            value, ensure_ascii=False, indent=2, allow_nan=False, default=json_default
        )
        + "\n"
    )


def verify_inputs(root):
    manifests = {}
    for name in SOURCES:
        directory = root / name
        path = directory / "download_manifest.json"
        data = json.loads(path.read_text())
        for file in data["files"]:
            if digest(directory / file["filename"]) != file["sha256"]:
                raise ValueError(
                    f"Downloaded source checksum changed: {name}/{file['filename']}"
                )
        for file in data["extracted_files"]:
            if digest(directory / file["path"]) != file["sha256"]:
                raise ValueError(
                    f"Extracted source checksum changed: {name}/{file['path']}"
                )
        manifests[name] = data
    return manifests


def report_markdown(results):
    frozen = results["metro_matched"]["frozen"]
    analog = results["metro_matched"]["analog"]
    hydraulic = results["hydraulic"]
    water = results["water"]
    smoke = results["nist_smoke"]

    def f(value):
        return "—" if value is None else f"{value:.3f}"

    lines = [
        "# Открытые источники: пригодность и пробные предсказания",
        "",
        (
            "Это разведочные эксперименты. Только `metro_frozen` применяет сохранённые модели VENA. "
            "Остальные модели обучены отдельно на части соответствующего открытого набора; "
            "они не заменяют production-артефакты и не подтверждают качество VENA."
        ),
        "",
        "| Источник | Что проверили | Для чего подходит | Чего не доказывает |",
        "|---|---|---|---|",
        (
            "| [MetroPT-3](https://archive.ics.uci.edu/dataset/791/metropt+3+dataset) | "
            "VENA pump_24h/72h и отдельный Isolation Forest по аналоговым измерениям | "
            "Исследование предвестников утечек компрессора | Качество на коллекторах Москвы |"
        ),
        (
            "| [UCI Hydraulic](https://archive.ics.uci.edu/dataset/447) | "
            "Степень утечки насоса 0/1/2 по завершённому циклу | Диагностика состояния насоса | "
            "Прогноз за 24–72 часа |"
        ),
        (
            "| [Urban Water](https://zenodo.org/records/15096167) | "
            "Попадание в окно ±7 дней вокруг утечки | Разведочный анализ SCADA и качества данных | "
            "Заблаговременное предупреждение об утечке |"
        ),
        (
            "| [NIST Smoke](https://www.nist.gov/el/fire/engineered-fire-safety/data-smoke-alarm-performance) | "
            "Срабатывание извещателя в ближайшие 10 секунд | Анализ реакции датчиков в лаборатории | "
            "Прогноз пожара за сутки и полевые показатели ложных тревог |"
        ),
        "",
        "## MetroPT: действующая VENA и аналоговые измерения",
        "",
        (
            "| Модель | AP | Доля положительных точек | Предупреждений после cooldown | "
            "Верных предупреждений | Замечено отказов |"
        ),
        "|---|---:|---:|---:|---:|---:|",
    ]
    for horizon in (24, 72):
        for name, metric, op in [
            (
                f"VENA pump_{horizon}h",
                frozen[f"pump_{horizon}h"],
                frozen[f"pump_{horizon}h"]["operations"],
            ),
            (
                f"Isolation Forest, {horizon}h",
                analog[str(horizon)]["metrics"],
                analog[str(horizon)]["operations"],
            ),
        ]:
            lines.append(
                f"| {name} | {f(metric['ap'])} | {f(metric['positive_rate'])} | "
                f"{op['alerts']} | {op['true_alerts']} | {op['covered_episodes']}/{op['episodes']} |"
            )
    lines += [
        "",
        (
            "Isolation Forest обучается только на феврале 2020; порог — 99-й процентиль обучающих оценок. "
            "Это показатель аномальности, не вероятность отказа. VENA использует сохранённые веса, калибраторы "
            "и пороги high. Период теста апрель–июль; четыре утечки относятся к одному компрессору. "
            "В таблице оба метода оценены на одинаковых временных точках с полной шестичасовой аналоговой историей. "
            "Полный прогон VENA сохранён отдельно в JSON. Метрики разных методов следует сопоставлять "
            "вместе с нагрузкой предупреждений; бюджеты тревог не выровнены."
        ),
        "",
        "## Гидравлический стенд",
        "",
        f"- {hydraulic['rows']} циклов; обучение {hydraulic['train_rows']}, тест {hydraulic['test_rows']}.",
        (
            "- Целиком отложены комбинации состояний охладителя, клапана и аккумулятора. "
            "Идентификаторы и целевые состояния не используются как признаки."
        ),
        (
            f"- Accuracy: **{f(hydraulic['metrics']['accuracy'])}**, balanced accuracy: "
            f"**{f(hydraulic['metrics']['balanced_accuracy'])}**, macro-F1: **{f(hydraulic['metrics']['macro_f1'])}**."
        ),
        (
            f"- Предсказание самого частого обучающего класса: accuracy "
            f"{f(hydraulic['metrics']['majority_accuracy'])}, balanced accuracy "
            f"{f(hydraulic['metrics']['majority_balanced_accuracy'])}."
        ),
        (
            "- Признаки используют весь 60-секундный цикл. Это оценка уже существующей утечки на одном стенде, "
            "а не прогноз будущего отказа на новой машине."
        ),
        "",
        "## Городская водопроводная сеть",
        "",
        (
            f"- {water['rows']} почасовых строк; обучение {water['train_rows']}, тест {water['test_rows']}. "
            f"Доля пропусков в используемых признаках: {water['missing_fraction']:.1%}."
        ),
        "- Обучение до 17.09.2022, тест с 01.10.2022; между ними 14 дней.",
        (
            f"- AP: **{f(water['metrics']['ap'])}**, доля положительных точек: "
            f"**{f(water['metrics']['positive_rate'])}**, ROC AUC: **{f(water['metrics']['roc_auc'])}**."
        ),
        (
            "- Метка охватывает и время после аварии. Причинность исходных anomaly scores неизвестна. "
            "Даже высокая метрика здесь не доказывала бы раннее предупреждение; нужны точные даты утечек "
            "и исходные измерения либо причинно рассчитанные признаки."
        ),
        "",
        "## Дымовые извещатели NIST",
        "",
        (
            f"- Загружено {smoke['smoke_box_files']} smoke-box и "
            f"{smoke['room_files_downloaded_not_scored']} room-файлов. В моделировании использовано "
            f"{smoke['used_files']} smoke-box экспериментов; исключено {len(smoke['rejected_files'])}."
        ),
        (
            f"- Тест: {smoke['test_experiments']} экспериментов, {len(smoke['test_detector_models'])} "
            "полностью отложенных моделей извещателей."
        ),
        (
            f"- AP по точкам перед тревогой: **{f(smoke['metrics']['ap'])}**, "
            f"доля положительных точек: **{f(smoke['metrics']['positive_rate'])}**."
        ),
        (
            f"- При фиксированном пороге 0.5 замечено **{smoke['covered_alarm_experiments']}/"
            f"{smoke['assessable_alarm_experiments']}** доступных тревог в окне 10 секунд. "
            f"В **{smoke['experiments_with_false_window_alerts']}** тестовых экспериментах были "
            "предупреждения, после которых тревога не наступала за 10 секунд."
        ),
        (
            "- Входы: оптическое затемнение, ионизационный ток, CO и прошлые окна 10 секунд. "
            "Текущий Alarm?, микрофон, номер эксперимента и время до тревоги не входят в признаки. "
            "Первые 10 секунд с документированным артефактом фильтра исключены."
        ),
        (
            "- Room-файлы скачаны и доступны для дальнейшей работы, но не имеют колонки Alarm?. "
            "Их не размечали автоматически по тем же сигналам, из которых строится прогноз."
        ),
        "",
        "## Практическое применение",
        "",
        (
            "Для VENA наиболее прямой внешний эксперимент — MetroPT с оговорками по домену и малому числу отказов. "
            "Hydraulic полезен для отдельного модуля диагностики по аналоговой телеметрии. "
            "NIST — для исследования реакции извещателей на горизонте секунд. "
            "Urban Water — для анализа аномалий; полноценный прогноз требует другой разметки."
        ),
        "",
        "## Воспроизведение",
        "",
        (
            "См. `ml/open_sources/README.md`. `protocol.json` фиксирует разбиения, параметры и хеши до расчётов; "
            "`sources.json` — URL, атрибуцию и контрольные суммы скачанного. Прогнозы сохранены в CSV; "
            "диагностические модели — рядом с отчётом. `report.json` содержит детали, группы теста "
            "и причины исключения файлов. Числа здесь — результат одного заранее заданного разбиения, "
            "без перебора лучших моделей/порогов по тесту и без заявлений о статистической значимости."
        ),
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=ROOT / "external_datasets")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results" / "open_sources_2026-10-20"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    print("Verifying downloaded and extracted input hashes...", flush=True)
    sources = verify_inputs(args.data_root)
    production_before = model_manifest(["pump_24h", "pump_72h"])
    files = [
        Path(__file__),
        *sorted((ROOT / "open_sources").glob("*.py")),
        ROOT / "validation" / "evaluation.py",
        ROOT / "validation" / "external.py",
        ROOT / "run_independent_validation.py",
        ROOT / "pipeline" / "features.py",
        ROOT / "pipeline" / "calibration.py",
    ]
    write_json(args.output / "sources.json", sources)
    write_json(
        args.output / "protocol.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "scope": "Exploratory suitability study; heterogeneous tasks, not a shared production benchmark",
            "python": platform.python_version(),
            "packages": {
                n: importlib.metadata.version(n)
                for n in [
                    "numpy",
                    "pandas",
                    "scikit-learn",
                    "joblib",
                    "lightgbm",
                    "catboost",
                ]
            },
            "source_sha256": {str(p.relative_to(ROOT)): digest(p) for p in files},
            "git_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "production": production_before,
            "hydraulic": {
                "grouping": "cooler/valve/accumulator combinations",
                "test_fraction": 0.25,
                "seed": 42,
                "parameters": experiments.HGB_PARAMS,
            },
            "water": {
                "train_end_exclusive": "2022-09-17",
                "test_start": "2022-10-01",
                "threshold": 0.5,
                "parameters": experiments.HGB_PARAMS,
            },
            "nist": {
                "grouping": "detector model",
                "test_fraction": 0.25,
                "seed": 42,
                "horizon_seconds": 10,
                "threshold": 0.5,
                "parameters": experiments.HGB_PARAMS,
            },
            "metro_analog": {
                "train_end_exclusive": "2020-03-01",
                "test_start": "2020-04-01",
                "test_end": "2020-08-01",
                "n_estimators": 200,
                "max_samples": 256,
                "seed": 42,
                "threshold_train_quantile": 0.99,
            },
        },
    )
    results = {}
    actions = {
        "metro_frozen": lambda: run_external(args.data_root / "metropt3", args.output),
        "metro_analog": lambda: experiments.metro_analog(args.data_root, args.output),
        "hydraulic": lambda: experiments.hydraulic(args.data_root, args.output),
        "water": lambda: experiments.water(args.data_root, args.output),
        "nist_smoke": lambda: experiments.nist_smoke(args.data_root, args.output),
    }
    for name, action in actions.items():
        print(f"Running {name}...", flush=True)
        results[name] = action()
        write_json(args.output / "report.json", results)
        print(f"Completed {name}", flush=True)
    results["metro_matched"] = experiments.metro_matched(args.output)
    if model_manifest(["pump_24h", "pump_72h"]) != production_before:
        raise RuntimeError("Production artifacts changed during experiment")
    results["production_artifacts_unchanged"] = True
    write_json(args.output / "report.json", results)
    (args.output / "REPORT.md").write_text(report_markdown(results))
    print(f"Report: {args.output / 'REPORT.md'}", flush=True)


if __name__ == "__main__":
    main()
