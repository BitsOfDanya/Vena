"""Periodically score frozen models; publish snapshots with an atomic rename."""
import os
from pathlib import Path
import subprocess
import time

output = Path("/srv/ml/results/predictions/snapshot.json")
output.parent.mkdir(parents=True, exist_ok=True)
mode = os.environ.get("VENA_ML_MODE", "demo")
if mode not in {"demo", "journal"}:
    raise SystemExit("VENA_ML_MODE must be demo or journal")
while True:
    temporary = output.with_suffix(".tmp.json")
    command = ["python", "score_snapshot.py", "--output", str(temporary)]
    if mode == "demo":
        command.append("--demo")
    subprocess.run(command, check=True)
    temporary.replace(output)
    time.sleep(int(os.environ.get("VENA_ML_REFRESH_SECONDS", "3600")))
