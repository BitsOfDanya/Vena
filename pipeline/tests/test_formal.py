import numpy as np
import pandas as pd

from pipeline import episodes as episodes_mod
from pipeline.formal import data, metrics


def test_formal_gap_zero_only_when_both_targets_met():
    assert metrics.formal_gap(0.7, 0.5) == 0.0
    assert metrics.formal_gap(0.9, 0.49) > 0.0
    assert metrics.formal_gap(0.69, 0.9) > 0.0
    assert abs(metrics.formal_gap(0.5, 0.3) - 0.4) < 1e-9


def test_frontier_reaches_target_on_separable_scores():
    y = np.array([1] * 50 + [0] * 150)
    s = np.concatenate([np.linspace(0.9, 1.0, 50), np.linspace(0.0, 0.5, 150)])
    out = metrics.frontier_metrics(y, s)
    assert out["formal_reached_oracle"]
    assert out["formal_gap_oracle"] == 0.0
    assert out["recall_at_precision_0.8"] == 1.0


def test_frontier_does_not_reach_target_on_random_scores():
    rng = np.random.default_rng(0)
    y = (rng.random(5000) < 0.1).astype(int)
    s = rng.random(5000)
    out = metrics.frontier_metrics(y, s)
    assert not out["formal_reached_oracle"]
    assert out["formal_gap_oracle"] > 0.3


def test_threshold_is_chosen_on_valid_only_and_applied_unchanged():
    rng = np.random.default_rng(1)
    y_valid = (rng.random(3000) < 0.2).astype(int)
    s_valid = y_valid * 0.3 + rng.random(3000)
    thr = metrics.pick_threshold(y_valid, s_valid)
    y_a = (rng.random(2000) < 0.2).astype(int)
    s_a = y_a * 0.3 + rng.random(2000)
    y_b = 1 - y_a
    out_a = metrics.transfer_metrics(y_valid, s_valid, y_a, s_a)
    out_b = metrics.transfer_metrics(y_valid, s_valid, y_b, s_a)
    assert out_a["threshold"] == thr == out_b["threshold"]
    assert out_a["alert_fraction"] == out_b["alert_fraction"]


def test_eval_at_threshold_counts():
    y = np.array([1, 1, 0, 0, 1])
    s = np.array([0.9, 0.8, 0.7, 0.1, 0.2])
    out = metrics.eval_at_threshold(y, s, 0.5)
    assert out["precision"] == 2 / 3
    assert out["recall"] == 2 / 3


def _episodes():
    return pd.DataFrame({
        "channel_id": ["a", "a", "b"],
        "episode_start": pd.to_datetime(["2024-01-02 00:00", "2024-01-10 00:00", "2024-01-05 12:00"]),
        "episode_end": pd.to_datetime(["2024-01-02 01:00", "2024-01-10 01:00", "2024-01-05 13:00"]),
    })


def test_time_to_next_failure_matches_assign_targets_for_every_horizon():
    cand = pd.DataFrame({
        "channel_id": ["a", "a", "a", "b", "b", "c"],
        "ts": pd.to_datetime(["2024-01-01 00:00", "2024-01-02 00:00", "2024-01-02 06:00",
                              "2024-01-04 12:00", "2024-01-06 00:00", "2024-01-01 00:00"]),
    })
    ep = _episodes()
    ttf = data.time_to_next_failure_hours(cand, ep)
    for h in (6, 24, 72, 168):
        expected = episodes_mod.assign_targets(cand, ep, h)["target"].values
        assert ((ttf <= h) == expected.astype(bool)).all()


def test_time_to_next_failure_never_uses_past_episodes():
    cand = pd.DataFrame({"channel_id": ["a"], "ts": pd.to_datetime(["2024-01-11 00:00"])})
    assert np.isnan(data.time_to_next_failure_hours(cand, _episodes())[0])


def test_protocol_masks_exclude_lockbox_years_from_train_and_valid():
    frame = pd.DataFrame({"ts": pd.to_datetime(["2024-06-01", "2025-06-01", "2026-03-01"])})
    train, valid = data.protocol_masks(frame)
    assert train.tolist() == [True, False, False]
    assert valid.tolist() == [False, True, False]


def test_event_bin_assignment():
    from pipeline.formal import hazard
    bins = hazard.event_bin(np.array([1.0, 6.0, 6.5, 24.0, 60.0, 72.0, 80.0, np.nan]))
    assert bins.tolist() == [0, 0, 1, 2, 4, 4, -1, -1]


def test_person_period_expansion_is_survival_consistent():
    from pipeline.formal import hazard
    ttf = np.array([5.0, 30.0, np.nan, 100.0])
    row_idx, bin_of_row, label = hazard.expand_person_period(None, ttf)
    by_cand = {i: (bin_of_row[row_idx == i].tolist(), label[row_idx == i].tolist()) for i in range(4)}
    assert by_cand[0] == ([0], [1])
    assert by_cand[1] == ([0, 1, 2, 3], [0, 0, 0, 1])
    assert by_cand[2] == ([0, 1, 2, 3, 4], [0, 0, 0, 0, 0])
    assert by_cand[3] == ([0, 1, 2, 3, 4], [0, 0, 0, 0, 0])


def test_cumulative_probability_matches_manual_product():
    from pipeline.formal import hazard
    h = np.array([[0.1, 0.2, 0.0, 0.0, 0.0]])
    assert abs(hazard.cumulative_probability(h, 1)[0] - (1 - 0.9 * 0.8)) < 1e-12


def test_research_frames_never_contain_lockbox_rows():
    frame = pd.DataFrame({"ts": pd.to_datetime(["2025-12-31 23:00", "2026-01-01 00:00", "2026-03-01 00:00"]), "v": [1, 2, 3]})
    out = data.drop_lockbox(frame)
    assert out["ts"].max() < data.LOCKBOX_START
    assert len(out) == 1


def test_lockbox_selection_is_lockbox_only_and_purges_final_horizon():
    from pipeline.formal import lockbox
    frame = pd.DataFrame({"ts": pd.to_datetime(["2025-12-31", "2026-01-01", "2026-06-01", "2026-06-29"])})
    out = lockbox.select_lockbox(frame, "2026-06-30 23:59:59", 72)
    assert out["ts"].tolist() == list(pd.to_datetime(["2026-01-01", "2026-06-01"]))


def test_lockbox_can_only_be_opened_once(tmp_path):
    import pytest
    from pipeline.formal import lockbox
    marker = tmp_path / "opened"
    marker.write_text("x")
    with pytest.raises(lockbox.LockboxAlreadyOpened):
        lockbox.open_lockbox("pump", 72, marker)


def test_hard_negative_weights_only_touch_train_negatives():
    from pipeline.formal import hardneg
    rng = np.random.default_rng(0)
    n = 4000
    ts = pd.to_datetime("2020-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 4 * 365 * 86400, n)), unit="s")
    frame = pd.DataFrame({"ts": ts, "f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    frame["target"] = (rng.random(n) < 0.2 + 0.2 * (frame["f1"] > 0)).astype(int)
    frame["y168"] = np.where(frame["target"] == 1, 1, (rng.random(n) < 0.3).astype(int))
    train = (frame["ts"].dt.year <= 2022).values
    w = hardneg.hard_negative_weights(frame, train, ["f1", "f2"], 4.0, "oof+near")
    assert (w[~train] == 1).all()
    assert (w[frame["target"].values == 1] == 1).all()
    assert (w[train & (frame["target"].values == 0)] >= 1).all()
    assert (w == 4.0).any()


def test_hard_negative_weights_ignore_future_labels():
    from pipeline.formal import hardneg
    rng = np.random.default_rng(1)
    n = 4000
    ts = pd.to_datetime("2020-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 4 * 365 * 86400, n)), unit="s")
    frame = pd.DataFrame({"ts": ts, "f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    frame["target"] = (rng.random(n) < 0.25).astype(int)
    frame["y168"] = frame["target"]
    train = (frame["ts"].dt.year <= 2022).values
    base = hardneg.hard_negative_weights(frame, train, ["f1", "f2"], 3.0, "oof")
    changed = frame.copy()
    future = (frame["ts"].dt.year > 2022).values
    changed.loc[future, "target"] = 1 - changed.loc[future, "target"]
    again = hardneg.hard_negative_weights(changed, train, ["f1", "f2"], 3.0, "oof")
    assert np.array_equal(base[train], again[train])
