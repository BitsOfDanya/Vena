import pandas as pd

from pipeline.targets import discovery


def _events():
    rows = []
    t0 = pd.Timestamp("2024-01-01")
    seq = [(0, "Норма"), (1, "Обесточен"), (2, "Обесточен"), (30, "Норма"), (31, "Обесточен"), (100, "Норма"), (101, "Обесточен")]
    for h, v in seq:
        rows.append(("a", t0 + pd.Timedelta(hours=h), v))
    rows.append(("b", t0 + pd.Timedelta(hours=5), "Обесточен"))
    return pd.DataFrame(rows, columns=["channel_id", "ts", "raw_value"])


def test_state_episodes_group_by_gap_and_count_ticks():
    ep = discovery.state_episodes(_events(), "Обесточен", gap_hours=6)
    a = ep[ep.channel_id == "a"].reset_index(drop=True)
    assert len(a) == 3
    assert a.loc[0, "n_ticks"] == 2
    assert a.loc[0, "episode_end"] - a.loc[0, "episode_start"] == pd.Timedelta(hours=1)
    assert (ep.channel_id == "b").sum() == 1


def test_episode_summary_recurrence_and_single_tick():
    ep = discovery.state_episodes(_events(), "Обесточен", gap_hours=6)
    s = discovery.episode_summary(ep)
    assert s["n_episodes"] == 4
    assert s["n_channels_with_episodes"] == 2
    assert abs(s["single_tick_fraction"] - 0.75) < 1e-9
    assert abs(s["recurring_le_7d"] - 0.5) < 1e-9


def test_horizon_base_rate_uses_only_future_starts():
    ev = _events()
    ep = discovery.state_episodes(ev, "Обесточен", gap_hours=6)
    rate_early = discovery.horizon_base_rate(ev[ev.ts < pd.Timestamp("2024-01-01 00:30")], ep, 2)
    assert rate_early == 1.0
    assert discovery.horizon_base_rate(ev[ev.ts > pd.Timestamp("2024-01-06")], ep, 48) == 0.0


def test_transition_counts_only_real_changes_within_channel():
    tr = discovery.transition_counts(_events())
    row = tr[(tr.prev_state == "Норма") & (tr.state == "Обесточен")]
    assert int(row["n"].iloc[0]) == 3
    assert not ((tr.prev_state == tr.state).any())
    assert tr["n"].sum() == 5


def test_sustained_onsets_require_dwell_and_use_only_onset_events():
    t0 = pd.Timestamp("2024-01-01")
    rows = [("a", 0, "Норма"), ("a", 10, "Обесточен"), ("a", 20, "Есть питание"), ("a", 600, "Обесточен"),
            ("a", 601, "Обесточен"), ("a", 5000, "Есть питание"), ("a", 6000, "Обесточен")]
    ev = pd.DataFrame([(c, t0 + pd.Timedelta(minutes=m), v) for c, m, v in rows], columns=["channel_id", "ts", "raw_value"])
    out = discovery.sustained_onsets(ev, "Обесточен", 30)
    assert out["episode_start"].tolist() == [t0 + pd.Timedelta(minutes=600)]
    short = discovery.sustained_onsets(ev, "Обесточен", 5)
    assert len(short) == 2


def test_sustained_onsets_drop_censored_final_state():
    t0 = pd.Timestamp("2024-01-01")
    ev = pd.DataFrame({"channel_id": ["a", "a"], "ts": [t0, t0 + pd.Timedelta(hours=1)],
                       "raw_value": ["Норма", "Обесточен"]})
    assert discovery.sustained_onsets(ev, "Обесточен", 1).empty
