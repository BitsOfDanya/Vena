"""Refreeze every production artifact on the corrected feature pipeline.

The follow-up research fixed a leak in ``channel_failure_prior`` and made the
event order deterministic, so artifacts frozen before 2026-09-28 were trained on
slightly different features than the scorer now computes. This script re-extracts
the event caches and refreezes each model with its original recipe, then
promotes the pump 72-hour blend and writes a fresh prediction snapshot.
"""

import os
import shutil
import subprocess
import sys
import time

from pipeline import config, extract

# (device, horizon, model) — recipes of the frozen artifacts in configs/models.
FINAL_MODELS = [
    ("pump", 24, "catboost"),
    ("fan", 24, "catboost"),
    ("fan", 72, "catboost"),
    ("smoke", 24, "catboost"),
]
SENSORS = ["pump", "fan", "smoke", "phase"]


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def run(*args):
    log("run " + " ".join(args))
    subprocess.run([sys.executable, *args], check=True, cwd=config.ROOT)


def main() -> None:
    import run_final_freeze

    stale = os.path.join(config.ANALYSIS_DIR, "ml_ready", "cache_before_20260928")
    for device in SENSORS:
        path = extract.cache_path(config.SENSOR_ALIASES[device])
        if os.path.exists(path):
            os.makedirs(stale, exist_ok=True)
            shutil.move(path, os.path.join(stale, os.path.basename(path)))
        extract.extract_events(config.SENSOR_ALIASES[device], force=True)
        log(f"extracted {device}")

    for device, horizon, model in FINAL_MODELS:
        run_final_freeze.run_final_for_device(config.SENSOR_ALIASES[device], device, horizon, model)
        log(f"frozen {device}_{horizon}h")
    # The previous pump_72h recipe stays available as the short-history fallback.
    run_final_freeze.run_final_for_device(config.SENSOR_ALIASES["pump"], "pump_baseline", 72, "logistic_regression")
    log("frozen pump_baseline_72h")

    run("run_pump_blend_freeze.py")
    run("run_power_freeze.py")
    run("score_snapshot.py")
    log("production refresh done")


if __name__ == "__main__":
    main()
