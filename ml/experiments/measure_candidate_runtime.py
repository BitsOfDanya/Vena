import argparse
import json
import os
import platform
import time
from pathlib import Path

import joblib
import pandas as pd

from pipeline import candidates, config, episodes, extract, features, training

SENSOR = "Состояние насоса"
MODEL_PATH = Path("artifacts/experimental/pump72_blend_20260924/model.joblib")
OUTPUT_PATH = Path("analysis/pump_runtime_predictions.parquet")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-extract", action="store_true")
    args = parser.parse_args()
    times = {}
    started = time.perf_counter()

    events = extract.extract_events(SENSOR, force=args.force_extract)
    times["event_extract_seconds"] = time.perf_counter() - started

    tick = time.perf_counter()
    history = episodes.build_episodes(events)
    generated = candidates.generate_candidates(events, SENSOR)
    latest = events["ts"].max() - pd.Timedelta(hours=72)
    selected = generated.loc[
        (generated["ts"].dt.year == 2026) & (generated["ts"] <= latest)
    ].copy()
    times["candidate_generation_seconds"] = time.perf_counter() - tick

    tick = time.perf_counter()
    rates = features.compute_global_rates(events, config.TRAIN_YEARS[1])
    prepared = features.compute_features(
        selected, events, history, global_rates=rates,
    )
    times["feature_preparation_seconds"] = time.perf_counter() - tick

    tick = time.perf_counter()
    model = joblib.load(MODEL_PATH)
    scores = model.predict_proba(prepared[training.feature_columns()])
    times["model_load_and_inference_seconds"] = time.perf_counter() - tick

    tick = time.perf_counter()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        pd.DataFrame({
            "channel_id": prepared["channel_id"].to_numpy(),
            "ts": prepared["ts"].to_numpy(),
            "score": scores,
        }).to_parquet(OUTPUT_PATH, index=False)
        times["output_write_seconds"] = time.perf_counter() - tick
        print(json.dumps({
            "mode": "raw_csv" if args.force_extract else "cached_events",
            "scope": "retrospective_2026h1_batch",
            "n_events": len(events), "n_candidates": len(prepared),
            "n_channels": prepared["channel_id"].nunique(),
            "cpu_count": os.cpu_count(), "machine": platform.machine(),
            "stages": {key: round(value, 3) for key, value in times.items()},
            "total_seconds": round(time.perf_counter() - started, 3),
        }))
    finally:
        OUTPUT_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
