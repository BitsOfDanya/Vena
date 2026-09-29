import json
import os

from pipeline import artifacts, config, recipes

MODELS = {
    "pump_24h": ("flooding", "Состояние насоса", "начало эпизода «Неисправен» за 24 ч"),
    "pump_72h": ("flooding", "Состояние насоса", "начало эпизода «Неисправен» за 72 ч"),
    "pump_baseline_72h": ("flooding", "Состояние насоса", "то же для каналов с историей меньше 30 сут"),
    "fan_24h": ("ventilation", "Состояние вентилятора", "начало эпизода «Неисправен» за 24 ч"),
    "fan_72h": ("ventilation", "Состояние вентилятора", "начало эпизода «Неисправен» за 72 ч"),
    "smoke_24h": ("fire", "Датчик дыма", "неисправность дымового датчика за 24 ч"),
    "smoke_alarm_24h": ("fire", "Датчик дыма", "срабатывание «Обнаружен дым» за 24 ч"),
    "phase_24h": ("power_loss", "Состояние фазы", "начало эпизода «Обесточен» за 24 ч"),
    "flood_24h": ("flooding", "Состояние насоса", "состояние камеры «Затоплен» за 24 ч"),
    "alarm_30m": ("false_alarms", "дым, газ, температура", "подтверждение тревоги за 30 мин"),
}
OUTPUT = os.path.join(config.ROOT, "results", "models.json")


def read(name):
    path = os.path.join(config.ROOT, "results", f"{name}.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def held_out(name, meta, refit, detection):
    study = refit.get(name)
    if study:
        side = study["refit"] if study.get("promoted") else study["current"]
        return {"period": study["recent"]["period"], "base_rate": study["recent"]["base_rate"],
                **{key: side.get(key) for key in ("avg_precision", "roc_auc", "precision_top5_per_day", "ece")}}
    if name == "smoke_alarm_24h" and detection:
        return {"period": detection["recent"]["period"], "base_rate": detection["recent"]["base_rate"],
                **{key: detection["refit"].get(key) for key in ("avg_precision", "roc_auc", "precision_top5_per_day", "ece")}}
    metrics = meta["metrics_snapshot"]
    test = metrics.get("test", {})
    calibrated = meta["model_config"].get("calibration") or metrics.get("calibration") or {}
    period = test.get("period") or ("2026H1" if name == "alarm_30m" else "2025-2026H1")
    return {"period": period,
            **{key: round(float(value), 4) if value is not None else None for key, value in (
                ("avg_precision", test.get("avg_precision", test.get("pr_auc"))),
                ("roc_auc", test.get("roc_auc")),
                ("ece", calibrated.get("ece_calibrated")))}}


def main() -> None:
    refit, report, detection = read("refit_study"), read("model_report"), read("detection_study")
    cards = []
    for name, (scenario, sensor, target) in MODELS.items():
        if not os.path.exists(os.path.join(artifacts.artifact_dir(name), "meta.json")):
            continue
        meta = artifacts.load_artifact(name)[1]
        model_config = meta["model_config"]
        operating = report.get(name, {})
        cards.append({
            "name": name,
            "scenario": scenario,
            "sensor": sensor,
            "target": target,
            "horizon_hours": model_config.get("horizon_hours"),
            "recipe": recipes.recipe_of(meta),
            "features": len(meta["feature_columns"]),
            "train_years": meta["training_period"]["train_years"],
            "version": meta.get("version"),
            "calibration": {key: (model_config.get("calibration") or meta["metrics_snapshot"].get("calibration") or {}).get(key)
                            for key in ("method", "fit_period")},
            "held_out": held_out(name, meta, refit, detection),
            "lead_time": operating.get("lead_time_2026h1", {}).get("high"),
            "daily_top_k": operating.get("daily_top_k_2026h1"),
            "drift_psi": operating.get("drift", {}).get("score_psi_reference_vs_2026h1"),
        })
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(cards, handle, indent=1, ensure_ascii=False)
    print(f"{len(cards)} models -> {OUTPUT}")


if __name__ == "__main__":
    main()
