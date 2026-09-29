"""Recompute health_history.json indexes with the production HI stretch.

Full rescore via run_health_history.py needs ml/dataset/ext-journal-*.csv.
When the journal is absent, this script remaps stored indexes through the
isotonic calibration inverse (left edge on plateaus) and effective_risk stretch
used by backend app.domain.health — so severe days compressed into the mid-40s
open up, matching live API. Points stuck on the ~55 plateau stay at 55 until a
full journal rescore can recover raw_risk.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
CALIBRATION = ROOT / "configs" / "health_index.json"
HISTORY = ROOT / "results" / "health_history.json"
JOURNALS = list((ROOT / "dataset").glob("ext-journal-*.csv")) if (ROOT / "dataset").is_dir() else []


def load_points() -> tuple[np.ndarray, np.ndarray]:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    return np.asarray(data["raw_risk"], dtype=float), np.asarray(data["risk"], dtype=float)


def left_inverse_raw(cal_target: float, xs: np.ndarray, ys: np.ndarray) -> float:
    """Smallest raw_risk whose calibrated risk is at least cal_target."""
    y_to_xmin: dict[float, float] = {}
    for x, y in zip(xs, ys, strict=True):
        key = round(float(y), 12)
        y_to_xmin.setdefault(key, float(x))
    ys_unique = np.array(sorted(y_to_xmin))
    xs_left = np.array([y_to_xmin[round(float(y), 12)] for y in ys_unique])
    return float(np.interp(cal_target, ys_unique, xs_left))


def effective_risk(raw: float, xs: np.ndarray, ys: np.ndarray) -> float:
    calibrated = float(np.interp(raw, xs, ys))
    if raw <= calibrated + 1e-9:
        return calibrated
    headroom = max(0.0, 1.0 - calibrated)
    if headroom <= 1e-9:
        return calibrated
    excess = min(1.0, (raw - calibrated) / headroom)
    return calibrated + excess * headroom * 0.9


def to_index(raw: float, xs: np.ndarray, ys: np.ndarray) -> int:
    return int(max(0, min(100, round(100 * (1.0 - effective_risk(raw, xs, ys))))))


def remap_index(hi: int, xs: np.ndarray, ys: np.ndarray) -> int:
    cal = (100 - int(hi)) / 100.0
    raw = left_inverse_raw(cal, xs, ys)
    return to_index(raw, xs, ys)


def remap_series(series: list, xs: np.ndarray, ys: np.ndarray) -> tuple[list, int]:
    out = []
    changed = 0
    for row in series:
        day, hi = row[0], int(row[1])
        new = remap_index(hi, xs, ys)
        if new != hi:
            changed += 1
        out.append([day, new])
    return out, changed


def full_rescore() -> None:
    print("Journal CSV present — running full run_health_history.main()", flush=True)
    from run_health_history import main

    main()


def offline_remap() -> None:
    xs, ys = load_points()
    report = json.loads(HISTORY.read_text(encoding="utf-8"))
    if report.get("stretch", {}).get("method") == "left_inverse_plus_effective_risk":
        print(f"Already remapped ({report['stretch'].get('changed_points')} points) — skip.", flush=True)
        return
    changed = 0
    total = 0
    objects = {}
    for object_id, days in report.get("objects", {}).items():
        remapped, delta = remap_series(days, xs, ys)
        objects[object_id] = remapped
        changed += delta
        total += len(days)
    sections = {}
    for group, days in report.get("sections", {}).items():
        remapped, delta = remap_series(days, xs, ys)
        sections[group] = remapped
        changed += delta
        total += len(days)
    report["objects"] = objects
    report["sections"] = sections
    report["basis"] = (
        "production models, each channel's latest 24-hour probability before midnight; "
        "HI stretch reapplied offline from stored indexes via calibration left-inverse "
        "(plateau ~55 kept until full journal rescore)"
    )
    report["stretch"] = {
        "method": "left_inverse_plus_effective_risk",
        "changed_points": changed,
        "total_points": total,
        "note": "Full discrimination on the HI=55 plateau requires python run_health_history.py with dataset/",
    }
    tmp = HISTORY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, HISTORY)
    print(f"Remapped {changed}/{total} points -> {HISTORY}", flush=True)


def main() -> None:
    if not HISTORY.is_file():
        sys.exit(f"missing {HISTORY}")
    if not CALIBRATION.is_file():
        sys.exit(f"missing {CALIBRATION}")
    if len(JOURNALS) >= 8:
        full_rescore()
        return
    print(
        f"Journal not found under {ROOT / 'dataset'} ({len(JOURNALS)} csv). "
        "Applying offline stretch remap.",
        flush=True,
    )
    offline_remap()


if __name__ == "__main__":
    main()
