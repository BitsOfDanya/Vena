"""Run three explicitly separated validation tracks without retraining.

Run from ml/: .venv/bin/python run_independent_validation.py
See validation/README.md for the real-data contract and interpretation.
"""

import argparse
import importlib.metadata
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from validation import external, simulation
from validation.evaluation import model_manifest, score_channel, sha256, summarize

ROOT = Path(__file__).resolve().parent
MODELS = ("pump_24h", "pump_72h", "flood_24h", "phase_24h")


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_real(manifest_path, output):
    if manifest_path is None:
        return {
            "status": "blocked_missing_data",
            "metrics": None,
            "reason": "No new SMVU event log and independent ODS/repair truth supplied.",
            "required": "Pass --real-manifest; see validation/real_manifest.example.json",
            "existing_2026H1_results_reused": False,
        }
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    required = {
        "events",
        "episodes",
        "model",
        "evaluation_start",
        "coverage_end",
        "attested_unseen",
        "truth_source",
        "timezone",
    }
    if required - manifest.keys():
        raise ValueError(
            f"Missing manifest fields: {sorted(required - manifest.keys())}"
        )
    if manifest["attested_unseen"] is not True:
        raise ValueError(
            "Real holdout requires explicit attestation that data were not used in development"
        )
    if manifest["model"] not in MODELS:
        raise ValueError("Unsupported real-data model")
    start, end = (
        pd.Timestamp(manifest["evaluation_start"]),
        pd.Timestamp(manifest["coverage_end"]),
    )
    if start.tzinfo is not None or end.tzinfo is not None:
        raise ValueError(
            "Use naive timestamps in the declared source timezone, without UTC offsets"
        )
    if start <= pd.Timestamp("2026-06-30 23:59:59") or end <= start:
        raise ValueError(
            "Real holdout must be after 2026-06-30 and have a positive covered period"
        )
    if not manifest["truth_source"] or not manifest["timezone"]:
        raise ValueError(
            "Independent truth source and source timezone must be documented"
        )
    if manifest["truth_source"].startswith("REPLACE"):
        raise ValueError("Replace the example truth_source with actual data provenance")
    ZoneInfo(manifest["timezone"])
    paths = {
        key: (manifest_path.parent / manifest[key]).resolve()
        for key in ("events", "episodes")
    }
    events = pd.read_csv(paths["events"], dtype={"channel_id": str}, parse_dates=["ts"])
    truth = pd.read_csv(
        paths["episodes"],
        dtype={"channel_id": str},
        parse_dates=["episode_start", "episode_end"],
    )
    for data, fields in (
        (events, ["channel_id", "ts", "raw_value", "alarm_flag"]),
        (truth, ["channel_id", "episode_start", "episode_end"]),
    ):
        if set(fields) - set(data.columns):
            raise ValueError(
                f"Missing CSV columns: {sorted(set(fields) - set(data.columns))}"
            )
    for data, columns in ((events, ["ts"]), (truth, ["episode_start", "episode_end"])):
        for column in columns:
            data[column] = pd.to_datetime(data[column])
            if data[column].dt.tz is not None:
                raise ValueError(
                    "CSV timestamps must be naive in the declared source timezone"
                )
    if events.empty or events.isna().any().any() or truth.isna().any().any():
        raise ValueError(
            "Events must be nonempty; missing input/ground-truth values are not accepted"
        )
    if (truth.episode_end < truth.episode_start).any():
        raise ValueError("Invalid ground-truth episode interval")
    for _, group in truth.groupby("channel_id"):
        ordered = group.sort_values("episode_start")
        if (ordered.episode_start < ordered.episode_end.shift()).any():
            raise ValueError("Merge overlapping physical episodes before evaluation")
    if set(truth.channel_id) - set(events.channel_id):
        raise ValueError("Ground truth references channels absent from events")
    if events.ts.max() > end or (len(truth) and truth.episode_end.max() > end):
        raise ValueError(
            "Inputs extend beyond declared coverage; select a coherent closed interval"
        )
    rows = []
    for channel, group in events.groupby("channel_id"):
        # Matching the actual production cold-start branch is supported, but
        # never invent a channel's history before its first observed event.
        channel_start = max(start, group.ts.min())
        rows.append(score_channel(group, truth, manifest["model"], channel_start, end))
    predictions = pd.concat(rows, ignore_index=True)
    predictions.to_csv(output / "real_predictions.csv.gz", index=False)
    return {
        "status": "completed",
        "scope": "new-period frozen model; independent truth per supplied manifest",
        "manifest": manifest,
        "input_sha256": {k: sha256(p) for k, p in paths.items()},
        "metrics": {manifest["model"]: summarize(predictions, truth)},
    }


def run_external(directory, output):
    events, truth, provenance = external.prepare(directory)
    end = min(
        pd.Timestamp(provenance["evaluation_end"]), pd.Timestamp(provenance["data_end"])
    )
    results, rows = {}, []
    for model in ("pump_24h", "pump_72h"):
        print(f"external: {model}", flush=True)
        predictions = score_channel(
            events, truth, model, provenance["evaluation_start"], end
        )
        results[model] = summarize(predictions, truth)
        rows.append(predictions)
    pd.concat(rows, ignore_index=True).to_csv(
        output / "external_predictions.csv.gz", index=False
    )
    truth.to_csv(output / "external_truth.csv", index=False)
    return {
        "status": "completed",
        "scope": "frozen-model cross-domain diagnostic, not independent Moscow accuracy",
        "provenance": provenance,
        "metrics": results,
    }


def seed_bootstrap(per_run, model):
    """Resample seeds, keeping paired scenarios/devices together; never IID rows."""
    seeds = sorted({r["seed"] for r in per_run})
    counts = np.zeros((len(seeds), 4))
    for i, seed in enumerate(seeds):
        for run in per_run:
            if run["seed"] == seed:
                op = run["metrics"][model]["operations"]
                counts[i] += [
                    op["true_alerts"],
                    op["alerts"],
                    op["covered_episodes"],
                    op["episodes"],
                ]
    rng = np.random.default_rng(1701)
    totals = counts[rng.integers(0, len(seeds), (1000, len(seeds)))].sum(axis=1)
    result = {
        "unit": "paired simulation seed across all scenarios",
        "resamples": 1000,
        "caution": "All-zero outcomes yield a degenerate [0,0] bootstrap interval; this does not prove zero population recall.",
    }
    for name, numerator, denominator in [("precision", 0, 1), ("episode_recall", 2, 3)]:
        valid = totals[:, denominator] > 0
        result[name + "_95pct"] = (
            np.quantile(
                totals[valid, numerator] / totals[valid, denominator], [0.025, 0.975]
            ).tolist()
            if valid.any() and len(seeds) > 1
            else None
        )
    return result


def run_simulation(seeds, output):
    all_predictions, all_truth, runs = [], [], []
    for scenario in simulation.SCENARIOS:
        for seed in seeds:
            print(f"simulation: {scenario}, seed={seed}", flush=True)
            sample = simulation.simulate(scenario, seed)
            events, truth = sample["events"], sample["truth"]
            run_predictions, run_metrics = [], {}
            for model in MODELS:
                kind = model.split("_")[0]
                target = truth.loc[truth.kind == kind]
                suffixes = (
                    ["phase"]
                    if kind == "phase"
                    else ["pump1"]
                    if kind == "flood"
                    else ["pump1", "pump2"]
                )
                parts = []
                for suffix in suffixes:
                    channel = sample["station"] + "/" + suffix
                    group = events.loc[events.channel_id == channel]
                    part = score_channel(
                        group, target, model, sample["start"], sample["end"]
                    )
                    parts.append(part)
                combined = pd.concat(parts, ignore_index=True)
                combined["scenario"], combined["seed"] = scenario, seed
                run_metrics[model] = summarize(combined, target)
                run_predictions.append(combined)
            runs.append(
                {
                    "scenario": scenario,
                    "seed": seed,
                    "station": sample["station"],
                    "parameters": sample["parameters"],
                    "metrics": run_metrics,
                }
            )
            all_predictions.extend(run_predictions)
            all_truth.append(truth)
            # A reproducible physical trace and event stream for each scenario.
            if seed == seeds[0]:
                sample_dir = output / "samples" / scenario
                sample_dir.mkdir(parents=True, exist_ok=True)
                events.to_csv(sample_dir / "events.csv.gz", index=False)
                truth.to_csv(sample_dir / "truth.csv", index=False)
                sample["physics"].to_csv(sample_dir / "physics.csv.gz", index=False)
    predictions = pd.concat(all_predictions, ignore_index=True)
    truth = pd.concat(
        [frame for frame in all_truth if not frame.empty], ignore_index=True
    )
    predictions.to_csv(output / "simulation_predictions.csv.gz", index=False)
    truth.to_csv(output / "simulation_truth.csv", index=False)
    metrics, by_scenario = {}, {}
    for model in MODELS:
        selected = predictions.loc[predictions.model == model]
        target = truth.loc[truth.kind == model.split("_")[0]]
        metrics[model] = summarize(selected, target)
        metrics[model]["bootstrap"] = seed_bootstrap(runs, model)
        by_scenario[model] = {
            scenario: summarize(group, target)
            for scenario, group in selected.groupby("scenario")
        }
    return {
        "status": "completed",
        "scope": "synthetic physical scenarios; not evidence of field accuracy",
        "stations": len(runs),
        "days_per_station": 90,
        "warmup_days": 30,
        "parameters_source": "Explicit engineering assumptions, not fitted to predictions or observed test results",
        "limitations": [
            "Simple mass balance; no pump curves or calibrated site geometry",
            "Fault/event times and scenario mix are artificial, not operational prevalence",
            "Only pump, flood and phase models tested; no fan/smoke/alarm model claims",
            "Offline ML test, not an API/UI latency or notification delivery test",
            "Bootstrap reflects simulator variation only, not uncertainty in real-world accuracy",
        ],
        "metrics": metrics,
        "by_scenario": by_scenario,
        "runs": runs,
    }


def render_report(report, output):
    lines = [
        "# Проверка замороженных моделей VENA",
        "",
        "Модели, калибраторы и пороги не переобучались и не подбирались по этим результатам.",
        "",
        "| Вариант | Статус | Что проверено |",
        "|---|---|---|",
        f"| Новый период СМВУ | {report['real']['status']} | Новый период и независимая разметка — только при наличии входных данных |",
        f"| MetroPT-3 | {report['external']['status']} | Перенос замороженных моделей на один компрессор |",
        f"| Физическая симуляция | {report['simulation']['status']} | Насосы, камера, питание; синтетическая оценка |",
        "",
        "AP и доля событий относятся к точкам прогноза каждые 6 часов. Precision/recall ниже относятся к предупреждениям/эпизодам при production-пороге high и cooldown 24 ч.",
        "Неполные будущие окна и точки внутри уже идущего физического эпизода исключены. Порог применяется к raw_score, калибратор — только к вероятности.",
        "",
        "| Вариант / модель | AP | Доля событий | Предупреждений | Precision | Эпизодов замечено | Упреждение, ч |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    def fmt(value):
        return "—" if value is None else f"{value:.3f}"

    for track in ("real", "external", "simulation"):
        for model, metric in (report[track].get("metrics") or {}).items():
            if "operations" not in metric:
                continue
            op = metric["operations"]
            lines.append(
                f"| {track} / {model} | {fmt(metric['ap'])} | {fmt(metric['positive_rate'])} | {op['alerts']} | {fmt(op['precision'])} | {op['covered_episodes']}/{op['episodes']} | {fmt(op['median_lead_hours'])} |"
            )
    lines.extend(
        [
            "",
            "## По сценариям симуляции",
            "",
            "| Модель | Сценарий | Замечено / эпизодов | Ложных предупреждений |",
            "|---|---|---:|---:|",
        ]
    )
    for model, scenarios in report["simulation"]["by_scenario"].items():
        for scenario, metric in scenarios.items():
            op = metric["operations"]
            if op["episodes"] or op["alerts"]:
                lines.append(
                    f"| {model} | {scenario} | {op['covered_episodes']}/{op['episodes']} | {op['false_alerts']} |"
                )
    lines.extend(
        [
            "",
            "## Интерпретация",
            "",
            "Внешний прогон оценивает перенос событийных моделей насосов на компрессор через фиксированный адаптер. Он не заменяет независимую проверку на СМВУ.",
            "Симулятор не подгонялся под обучающие данные: в нём нет многолетней истории повторяющихся отказов. Внезапный отказ и отключение питания заданы без предвестников; отсутствие их прогноза само по себе не доказывает дефект алгоритма. Деградация, напротив, меняет циклы откачки, но штатная модель pump_72h не использует duty-cycle-признаки.",
            "Нулевой охват при штатном пороге означает, что перенос с текущими признаками и порогами не подтверждён. Менять пороги по этим результатам и затем называть их независимым тестом нельзя.",
            "",
            "## Ограничения",
            "",
            "- Без новой выгрузки нельзя заключить, что модели подтвердили качество на независимом периоде СМВУ.",
            "- MetroPT уже изучался в проекте. Этот прогон проверяет замороженные production-модели с явным адаптером; это не новый закрытый тест. Четырёх отказов одного агрегата недостаточно для надёжной оценки переноса.",
            "- Симуляция не подтверждает реальные precision/recall и не доказывает экономический эффект.",
            "- Простой baseline: число наблюдавшихся целевых эпизодов за 7 суток; правило предупреждает при значении > 0. Его нагрузка не выравнивается с моделью и показана отдельно в JSON.",
            "- В признаках используются только эпизоды из наблюдаемых событий. Отдельная таблица истинных отказов доступна исключительно оценщику.",
            "",
            "## Артефакты",
            "",
            "- `protocol.json`: заранее зафиксированные параметры, версии окружения и SHA-256 моделей.",
            "- `report.json`: подробные метрики, сценарии, bootstrap по seed и происхождение данных.",
            "- `*_predictions.csv.gz`, `*_truth.csv`: прогнозы и исходы для воспроизведения расчётов.",
            "- `samples/`: физические траектории и события первого seed каждого сценария.",
            "",
        ]
    )
    (output / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results" / "independent_validation"
    )
    parser.add_argument(
        "--metropt-dir", type=Path, default=ROOT / "external_datasets" / "metropt3"
    )
    parser.add_argument("--real-manifest", type=Path)
    parser.add_argument("--seeds", type=int, nargs="+", default=list(range(101, 109)))
    args = parser.parse_args()
    if len(args.seeds) != len(set(args.seeds)):
        parser.error("Seeds must be unique")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = model_manifest(MODELS)
    protocol = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "models": manifest,
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            str(p.relative_to(ROOT)): sha256(p)
            for p in [
                Path(__file__),
                *sorted((ROOT / "validation").glob("*.py")),
                ROOT / "pipeline" / "features.py",
                ROOT / "pipeline" / "calibration.py",
                ROOT / "pipeline" / "targets" / "discovery.py",
            ]
        },
        "python": platform.python_version(),
        "packages": {
            n: importlib.metadata.version(n)
            for n in (
                "numpy",
                "pandas",
                "scikit-learn",
                "lightgbm",
                "catboost",
                "joblib",
            )
        },
        "score_frequency": "6h",
        "cooldown_hours": 24,
        "threshold": "artifact high on raw_score",
        "seeds": args.seeds,
        "scenarios": simulation.SCENARIOS,
        "external_start": "2020-04-01",
        "external_end": "2020-08-01",
        "retraining": False,
        "test_threshold_selection": False,
        "confidence_intervals": "simulation: paired-seed bootstrap; external: not reported (one machine, four events)",
    }
    write_json(args.output / "protocol.json", protocol)
    report = {"protocol": "protocol.json"}
    # Persist each completed track so a later failure never erases its evidence.
    for name, action in [
        ("real", lambda: run_real(args.real_manifest, args.output)),
        ("external", lambda: run_external(args.metropt_dir, args.output)),
        ("simulation", lambda: run_simulation(args.seeds, args.output)),
    ]:
        report[name] = action()
        write_json(args.output / "report.json", report)
        print(f"{name}: {report[name]['status']}", flush=True)
    if model_manifest(MODELS) != manifest:
        raise RuntimeError("Production artifacts changed during validation")
    report["production_artifacts_unchanged"] = True
    write_json(args.output / "report.json", report)
    render_report(report, args.output)
    print(f"Report: {args.output / 'REPORT.md'}", flush=True)


if __name__ == "__main__":
    main()
