import argparse

import pandas as pd

from experiments.common import emit, validation_mask
from experiments.run_recency_experiment import cache_paths

EVENT_CACHES = {
    "fan": "analysis/ml_ready/cache/events_Состояние_вентилятора.parquet",
    "pump": "analysis/ml_ready/cache/events_Состояние_насоса.parquet",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=tuple(EVENT_CACHES), required=True)
    args = parser.parse_args()
    events = pd.read_parquet(
        EVENT_CACHES[args.sensor], columns=["channel_id", "ts", "raw_value"],
    )
    same_second = events.groupby(["channel_id", "ts"], observed=True).agg(
        n_events=("raw_value", "size"),
        n_states=("raw_value", "nunique"),
    )
    cache, _, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache, columns=["channel_id", "ts", "target"])
    frame = frame.join(same_second, on=["channel_id", "ts"])
    for year in (2025, 2026):
        valid = frame.loc[validation_mask(frame, year)]
        multi_event = valid["n_events"].fillna(0) > 1
        multi_state = valid["n_states"].fillna(0) > 1
        emit({
            "sensor": args.sensor,
            "valid_year": year,
            "n_candidates": len(valid),
            "n_positive": int(valid["target"].sum()),
            "n_same_second_multi_event": int(multi_event.sum()),
            "n_same_second_multi_state": int(multi_state.sum()),
            "n_positive_same_second_multi_event": int(valid.loc[multi_event, "target"].sum()),
            "n_positive_same_second_multi_state": int(valid.loc[multi_state, "target"].sum()),
        })


if __name__ == "__main__":
    main()
