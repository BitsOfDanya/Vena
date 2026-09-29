import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import config, extract
from pipeline.targets import access

OUTPUT = os.path.join(config.ROOT, "results", "access_analysis.json")
CONFIG = os.path.join(config.ROOT, "configs", "access.json")
FLAGS_PER_DAY = 5


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load():
    dictionary = extract.channel_dictionary()
    tag_by_channel = dict(zip(dictionary.iloc[:, 0].astype(str), dictionary.iloc[:, 3], strict=True))
    guard = access.guard_states(extract.extract_events(access.GUARD_SENSOR), tag_by_channel)
    parts = [access.triggers(extract.extract_events(sensor), sensor, tag_by_channel) for sensor in access.ACCESS_SENSORS]
    return pd.concat(parts, ignore_index=True), guard


def main() -> None:
    triggers, guard = load()
    log(f"triggers {len(triggers)}, guard changes {len(guard)}")
    scored = access.assess(triggers, guard)
    days = max((scored["ts"].max() - scored["ts"].min()).days, 1)
    threshold = float(np.quantile(scored["index"], 1 - min(FLAGS_PER_DAY * days / len(scored), 1.0)))
    flagged = scored["index"] >= threshold
    everything = pd.Series(True, index=scored.index)

    def share(mask, column):
        return round(float(scored.loc[mask, column].mean()), 4)

    by_year = (
        scored.assign(year=scored["ts"].dt.year, flagged=flagged)
        .groupby("year")
        .agg(armed_triggers=("index", "size"), flagged=("flagged", "sum"))
        .astype(int)
        .reset_index()
        .to_dict("records")
    )
    by_sensor = (
        scored.assign(flagged=flagged)
        .groupby("sensor_type")
        .agg(armed_triggers=("index", "size"), flagged=("flagged", "sum"))
        .astype(int)
        .reset_index()
        .to_dict("records")
    )
    report = {
        "entry_triggers_total": int(len(triggers)),
        "armed_triggers": int(len(scored)),
        "armed_share": round(len(scored) / max(len(triggers), 1), 4),
        "armed_triggers_per_day": round(len(scored) / days, 1),
        "flag_threshold": round(threshold, 4),
        "flagged": int(flagged.sum()),
        "flagged_per_day": round(float(flagged.sum()) / days, 2),
        "weights": access.WEIGHTS,
        "by_year": by_year,
        "by_sensor": by_sensor,
        "flagged_profile": {
            "night_share": {"flagged": share(flagged, "night"), "all_armed": share(everything, "night")},
            "breach_sensor_share": {"flagged": share(flagged, "breach_sensor"), "all_armed": share(everything, "breach_sensor")},
            "chain_share": {"flagged": share(flagged, "chain"), "all_armed": share(everything, "chain")},
            "objects_with_flags": int(scored.loc[flagged, "object"].nunique()),
        },
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False, default=float)
    with open(CONFIG, "w", encoding="utf-8") as handle:
        json.dump({"flag_threshold": report["flag_threshold"], "weights": access.WEIGHTS}, handle, indent=2)
    log(json.dumps(report, indent=1, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main()
