import json
import os
from pathlib import Path
import subprocess
import time

output = Path("/srv/ml/results/predictions/snapshot.json")
output.parent.mkdir(parents=True, exist_ok=True)
heartbeat = output.parent / "heartbeat"
dataset = Path("/srv/ml/dataset")
mode = os.environ.get("VENA_ML_MODE", "auto")
if mode not in {"demo", "journal", "auto"}:
    raise SystemExit("VENA_ML_MODE must be demo, journal or auto")


def status(state, detail):
    path = output.parent / "worker-status.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"mode": mode, "state": state, "detail": detail}), encoding="utf-8")
    temporary.replace(path)


if mode == "demo":
    while True:
        temporary = output.with_suffix(".tmp.json")
        subprocess.run(["python", "score_snapshot.py", "--demo", "--output", str(temporary)], check=True)
        temporary.replace(output)
        heartbeat.write_text(str(time.time()), encoding="utf-8")
        status("demo", "Демонстрационные данные")
        time.sleep(int(os.environ.get("VENA_ML_REFRESH_SECONDS", "3600")))

process = None
previous = None
while True:
    heartbeat.write_text(str(time.time()), encoding="utf-8")
    files = sorted([*dataset.glob("ext-journal-*.csv"), *dataset.glob("uploads/ext-journal-*.csv")])
    reference = dataset / "справочник_каналов_датчиков.csv"
    marker = dataset / ".revision"
    revision = (marker.read_text() if marker.exists() else "", reference.stat().st_mtime_ns if reference.exists() else 0,
                tuple((file.name, file.stat().st_size, file.stat().st_mtime_ns) for file in files))
    ready = reference.exists() and bool(files)
    if revision != previous:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        previous = revision
        process = None
        if ready:
            output.unlink(missing_ok=True)
            for file in Path("/srv/ml/analysis/ml_ready/cache").glob("events_*.parquet"):
                file.unlink()
            status("processing", "Обрабатывается реальный журнал")
            process = subprocess.Popen(["python", "stream_scoring.py"], env={**os.environ, "VENA_ML_MODE": "journal", "VENA_SNAPSHOT_PATH": str(output)})
        else:
            output.unlink(missing_ok=True)
            status("waiting", "Загрузите справочник каналов и реальный журнал")
    elif process and process.poll() is not None:
        status("error", "Обработка журнала завершилась с ошибкой. Проверьте журнал ML-контейнера.")
    elif ready and output.exists():
        status("journal", "Прогнозы по реальным каналам")
    time.sleep(5)
