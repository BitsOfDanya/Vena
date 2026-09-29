import json

import pandas as pd

from experiments.run_recency_experiment import cache_paths
from pipeline import config

EVENT_CACHE = "analysis/ml_ready/cache/events_Состояние_вентилятора.parquet"


def main():
    cache, episodes_cache, _ = cache_paths("fan", False)
    frame = pd.read_parquet(cache, columns=["channel_id", "ts", "target", "trigger"])
    episodes = pd.read_parquet(episodes_cache, columns=["channel_id", "episode_start"])
    focus = frame.loc[(frame["ts"].dt.year == 2026) & (frame["ts"].dt.month == 5)]
    cohort_ids = focus["channel_id"].value_counts().head(10).index
    cohort = frame.loc[frame["channel_id"].isin(cohort_ids)]
    cohort_episodes = episodes.loc[episodes["channel_id"].isin(cohort_ids)]
    events = pd.read_parquet(
        EVENT_CACHE, columns=["channel_id", "raw_value", "alarm_flag"],
    )
    cohort_events = events.loc[events["channel_id"].isin(cohort_ids)]
    other_events = events.loc[~events["channel_id"].isin(cohort_ids)]
    history = cohort.loc[cohort["ts"].dt.year < 2026]
    result = {
        "selection": "top10_channels_by_may_2026_candidate_count",
        "n_channels": len(cohort_ids),
        "may_2026_candidates": int(focus["channel_id"].isin(cohort_ids).sum()),
        "may_2026_positive": int(focus.loc[focus["channel_id"].isin(cohort_ids), "target"].sum()),
        "history_before_2026_candidates": len(history),
        "history_before_2026_positive": int(history["target"].sum()),
        "all_observed_failure_episodes": len(cohort_episodes),
        "cohort_n_events": len(cohort_events),
        "cohort_n_distinct_states": int(cohort_events["raw_value"].nunique()),
        "cohort_n_fault_state_events": int(
            (cohort_events["raw_value"] == config.FAULT_LITERAL).sum()
        ),
        "cohort_alarm_fraction": float(cohort_events["alarm_flag"].mean()),
        "other_alarm_fraction": float(other_events["alarm_flag"].mean()),
        "by_year": [
            {
                "year": int(year),
                "n_candidates": len(group),
                "n_positive": int(group["target"].sum()),
                "n_failure_episodes": int(
                    (cohort_episodes["episode_start"].dt.year == year).sum()
                ),
            }
            for year, group in cohort.groupby(cohort["ts"].dt.year)
        ],
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
