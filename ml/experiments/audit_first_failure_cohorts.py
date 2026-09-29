import argparse

import pandas as pd

from experiments.common import emit
from experiments.run_recency_experiment import cache_paths

EVENT_CACHES = {
    "fan": "analysis/ml_ready/cache/events_Состояние_вентилятора.parquet",
    "pump": "analysis/ml_ready/cache/events_Состояние_насоса.parquet",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", choices=tuple(EVENT_CACHES), required=True)
    args = parser.parse_args()
    events = pd.read_parquet(EVENT_CACHES[args.sensor], columns=["channel_id", "ts"])
    candidate_cache, episode_cache, _ = cache_paths(args.sensor, False)
    candidates = pd.read_parquet(candidate_cache, columns=["channel_id", "ts"])
    candidate_times = {
        channel: group["ts"]
        for channel, group in candidates.groupby("channel_id", observed=True)
    }
    episodes = pd.read_parquet(episode_cache, columns=["channel_id", "episode_start"])
    first_seen = events.groupby("channel_id", observed=True)["ts"].min()
    first_failure = episodes.groupby("channel_id", observed=True)["episode_start"].min()
    last_year = int(events["ts"].max().year)
    for year in range(int(events["ts"].min().year) + 1, last_year + 1):
        start = pd.Timestamp(f"{year}-01-01")
        end = pd.Timestamp(f"{year + 1}-01-01")
        active = set(events.loc[
            (events["ts"] >= start) & (events["ts"] < end), "channel_id"
        ])
        new = {channel for channel in active if first_seen[channel] >= start}
        first = {
            channel for channel in active
            if channel in first_failure.index
            and start <= first_failure[channel] < end
        }
        new_first = list(new & first)
        lag_hours = (
            (first_failure.reindex(new_first) - first_seen.reindex(new_first))
            .dt.total_seconds() / 3600
        )
        first_episode_covered = sum(
            (
                (candidate_times[channel] < first_failure[channel])
                & (candidate_times[channel] >= first_failure[channel] - pd.Timedelta(hours=72))
            ).any()
            for channel in new_first
            if channel in candidate_times
        )
        emit({
            "sensor": args.sensor,
            "year": year,
            "observed_until": min(end, events["ts"].max()).date().isoformat(),
            "n_active_channels": len(active),
            "n_new_channels": len(new),
            "n_first_failure_channels": len(first),
            "n_new_channels_with_first_failure": len(new_first),
            "n_existing_channels_with_first_failure": len(first - new),
            "n_new_first_failure_within_72h_of_first_event": int((lag_hours <= 72).sum()),
            "n_new_first_failure_at_first_event": int((lag_hours == 0).sum()),
            "n_new_first_failures_with_prior_72h_candidate": int(first_episode_covered),
            "median_new_first_failure_lag_hours": (
                float(lag_hours.median()) if len(lag_hours) else None
            ),
        })


if __name__ == "__main__":
    main()
