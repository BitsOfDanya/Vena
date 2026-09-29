import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from pipeline import artifacts, config, extract
from pipeline.targets import access

TOLERANCE = 0.005
SENSOR_TYPES = [config.SENSOR_ALIASES[key] for key in ("pump", "fan", "smoke", "phase")] + [
    *access.ACCESS_SENSORS,
    access.GUARD_SENSOR,
]
FINAL_MODELS = [
    ("pump", 24, "catboost"),
    ("fan", 24, "catboost"),
    ("fan", 72, "catboost"),
    ("smoke", 24, "catboost"),
]
SCRIPTS = [
    ("run_pump_blend_freeze.py", ["pump_72h"]),
    ("run_power_freeze.py", ["phase_24h"]),
    ("run_flood_freeze.py", ["flood_24h"]),
    ("run_alarm_freeze.py", ["alarm_30m"]),
]


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def run(*args):
    log("run " + " ".join(args))
    subprocess.run([sys.executable, *args], check=True, cwd=config.ROOT)


def quality(name):
    path = os.path.join(artifacts.artifact_dir(name), "meta.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        meta = json.load(handle)
    years = (meta.get("training_period") or {}).get("train_years")
    if years and int(years.split("-")[-1]) > config.TRAIN_YEARS[1] + 1:
        return None
    metrics = meta["metrics_snapshot"]
    if "variants" in metrics:
        return metrics["variants"][metrics["selected"]]["test"]["pr_auc"]
    test = metrics.get("test") or {}
    for key in ("avg_precision", "pr_auc"):
        if key in test:
            return test[key]
    return metrics.get("valid", {}).get("pr_auc")


def challenge(names, refit):
    backup = tempfile.mkdtemp(prefix="vena-champion-")
    before = {}
    for name in names:
        before[name] = quality(name)
        if before[name] is not None:
            shutil.copytree(artifacts.artifact_dir(name), os.path.join(backup, name))
            config_path = os.path.join(config.ROOT, "configs", "models", f"{name}.json")
            if os.path.exists(config_path):
                shutil.copy2(config_path, os.path.join(backup, f"{name}.json"))
    refit()
    for name in names:
        after = quality(name)
        if before[name] is not None and (after is None or after < before[name] - TOLERANCE):
            shutil.rmtree(artifacts.artifact_dir(name))
            shutil.copytree(os.path.join(backup, name), artifacts.artifact_dir(name))
            saved_config = os.path.join(backup, f"{name}.json")
            if os.path.exists(saved_config):
                shutil.copy2(saved_config, os.path.join(config.ROOT, "configs", "models", f"{name}.json"))
            log(f"{name}: challenger {after} < champion {before[name]}, champion kept")
        else:
            log(f"{name}: {before[name]} -> {after}")
    shutil.rmtree(backup)


def main() -> None:
    import run_final_freeze

    for sensor_type in SENSOR_TYPES:
        extract.extract_events(sensor_type, force=True)
        log(f"extracted {sensor_type}")

    for device, horizon, model in FINAL_MODELS:
        challenge(
            [f"{device}_{horizon}h"],
            lambda d=device, h=horizon, m=model: run_final_freeze.run_final_for_device(config.SENSOR_ALIASES[d], d, h, m),
        )
    challenge(
        ["pump_baseline_72h"],
        lambda: run_final_freeze.run_final_for_device(config.SENSOR_ALIASES["pump"], "pump_baseline", 72, "logistic_regression"),
    )
    for script, names in SCRIPTS:
        challenge(names, lambda s=script: run(s))

    run("run_calibration.py")
    run("run_refit_study.py", "--promote")
    run("run_detection_study.py", "--freeze")
    run("run_model_report.py")
    run("run_incident_calibration.py")
    run("run_health_index.py")
    run("run_access_analysis.py")
    run("run_seasonality.py")
    run("run_workload_forecast.py")
    run("run_alarm_kpis.py")
    run("build_model_registry.py")
    run("score_snapshot.py")
    log("production refresh done")


if __name__ == "__main__":
    main()
