import numpy as np
import pandas as pd

from pipeline.targets import state_target as st


def _events():
    t0 = pd.Timestamp("2024-03-01")
    rows = []
    for ch in ["a", "b"]:
        for i, (h, v) in enumerate([(0, "Норма"), (10, "Есть питание"), (20, "Обесточен"), (21, "Обесточен"),
                                    (60, "Есть питание"), (100, "Норма"), (140, "Обесточен")]):
            rows.append((ch, t0 + pd.Timedelta(hours=h), 0, v))
    return pd.DataFrame(rows, columns=["channel_id", "ts", "alarm_flag", "raw_value"])


def test_candidates_never_lie_inside_target_state():
    ev = _events()
    cand = st.event_candidates(ev, "Обесточен", silence=False)
    assert len(cand) > 0
    merged = cand.merge(ev, on=["channel_id", "ts"])
    assert (merged["raw_value"] != "Обесточен").all()


def test_horizon_targets_use_only_future_episode_starts():
    ev = _events()
    frame, episodes = st.build_frame(ev, "Обесточен", horizons=(6, 24, 72), silence=False)
    t0 = pd.Timestamp("2024-03-01")
    row = frame[(frame.channel_id == "a") & (frame.ts == t0 + pd.Timedelta(hours=10))].iloc[0]
    assert row["y6"] == 0 and row["y24"] == 1 and row["y72"] == 1
    late = frame[(frame.channel_id == "a") & (frame.ts == t0 + pd.Timedelta(hours=100))].iloc[0]
    assert late["y24"] == 0 and late["y72"] == 1


def test_boundary_episode_start_is_not_positive_at_same_timestamp():
    ev = _events()
    frame, _ = st.build_frame(ev, "Обесточен", horizons=(24,), silence=False)
    t0 = pd.Timestamp("2024-03-01")
    at_start = frame[(frame.channel_id == "a") & (frame.ts == t0 + pd.Timedelta(hours=20))]
    assert at_start.empty


def test_features_do_not_change_when_future_events_are_altered():
    ev = _events()
    base, _ = st.build_frame(ev, "Обесточен", horizons=(24,), silence=False)
    changed = ev.copy()
    late = changed["ts"] > pd.Timestamp("2024-03-01") + pd.Timedelta(hours=100)
    changed.loc[late, "raw_value"] = "Норма"
    again, _ = st.build_frame(changed, "Обесточен", horizons=(24,), silence=False)
    cutoff = pd.Timestamp("2024-03-01") + pd.Timedelta(hours=100)
    cols = ["events_1h", "events_24h", "alarms_24h", "time_since_last_event_hours", "failures_7d",
            "time_since_last_failure_days"]
    a = base[base.ts <= cutoff].set_index(["channel_id", "ts"])[cols]
    b = again[again.ts <= cutoff].set_index(["channel_id", "ts"])[cols]
    assert a.equals(b)


def test_lockbox_rows_are_dropped():
    ev = _events()
    ev = pd.concat([ev, pd.DataFrame({"channel_id": ["a"], "ts": [pd.Timestamp("2026-02-01")], "alarm_flag": [0],
                                       "raw_value": ["Норма"]})], ignore_index=True)
    frame, _ = st.build_frame(ev, "Обесточен", horizons=(24,), silence=False)
    assert frame["ts"].max() < st.LOCKBOX_START
