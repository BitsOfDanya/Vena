"""ML worker: demo snapshots on a timer, or the journal stream scorer.

demo    — synthetic stand channels are scored by the frozen models every
          VENA_ML_REFRESH_SECONDS and published with an atomic rename.
journal — the SMVU journal in /srv/ml/dataset is scored once, then event batches
          posted to the API are rescored within seconds (stream_scoring.py).
Both modes touch results/predictions/heartbeat, which the healthcheck reads.
"""
import os
from pathlib import Path
import subprocess
import time

output = Path("/srv/ml/results/predictions/snapshot.json")
output.parent.mkdir(parents=True, exist_ok=True)
heartbeat = output.parent / "heartbeat"
mode = os.environ.get("VENA_ML_MODE", "demo")
if mode not in {"demo", "journal"}:
    raise SystemExit("VENA_ML_MODE must be demo or journal")

if mode == "journal":
    os.environ.setdefault("VENA_SNAPSHOT_PATH", str(output))
    import stream_scoring

    stream_scoring.main()

while True:
    temporary = output.with_suffix(".tmp.json")
    subprocess.run(["python", "score_snapshot.py", "--demo", "--output", str(temporary)], check=True)
    temporary.replace(output)
    heartbeat.write_text(str(time.time()), encoding="utf-8")
    time.sleep(int(os.environ.get("VENA_ML_REFRESH_SECONDS", "3600")))
