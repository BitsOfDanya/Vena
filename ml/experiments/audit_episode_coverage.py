import argparse

import pandas as pd

from experiments.common import emit, validation_mask
from experiments.run_recency_experiment import cache_paths
from pipeline.alerts import candidate_coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=("pump", "fan"), default="pump")
    parser.add_argument("--years", default="2024,2025")
    args = parser.parse_args()
    cache, episodes_cache, _ = cache_paths(args.sensor, False)
    frame = pd.read_parquet(cache, columns=["channel_id", "ts", "target"])
    episodes = pd.read_parquet(episodes_cache)
    for year in map(int, args.years.split(",")):
        valid = frame.loc[validation_mask(frame, year)]
        starts = episodes.loc[
            (episodes["episode_start"] >= valid["ts"].min())
            & (episodes["episode_start"] <= valid["ts"].max())
        ]
        covered = candidate_coverage(valid[["channel_id", "ts"]], starts, 72)
        emit({
            "sensor": args.sensor, "year": year,
            "n_candidates": len(valid), "n_positive_candidates": int(valid["target"].sum()),
            "n_episodes": len(starts), "n_covered_episodes": int(covered.sum()),
            "candidate_coverage": float(covered.mean()) if len(covered) else None,
        })


if __name__ == "__main__":
    main()
