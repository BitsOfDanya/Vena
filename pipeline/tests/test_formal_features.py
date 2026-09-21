import numpy as np
import pandas as pd

from pipeline import config
from pipeline.formal import features_ext as fx

STATES = ["Включен", "Выключен", "Норма", config.FAULT_LITERAL]


def _events(seed, n=400, start="2024-01-01", days=40):
    rng = np.random.default_rng(seed)
    rows = []
    t0 = pd.Timestamp(start)
    for ch in ["a", "b", "c"]:
        secs = np.sort(rng.integers(0, days * 86400, n))
        for s in secs:
            rows.append((ch, t0 + pd.Timedelta(seconds=int(s)), int(rng.random() < 0.2), STATES[rng.integers(0, 4)]))
    return pd.DataFrame(rows, columns=["channel_id", "ts", "alarm_flag", "raw_value"])


def _cand(events, cutoff, n=60, seed=5):
    rng = np.random.default_rng(seed)
    parts = []
    for ch in ["a", "b", "c"]:
        lo = events["ts"].min() + pd.Timedelta(days=2)
        secs = np.sort(rng.integers(0, int((cutoff - lo).total_seconds()), n))
        parts.append(pd.DataFrame({"channel_id": ch, "ts": [lo + pd.Timedelta(seconds=int(s)) for s in secs]}))
    return pd.concat(parts, ignore_index=True)


def _perturb_future(events, cutoff, seed=9):
    rng = np.random.default_rng(seed)
    e = events.copy()
    late = e["ts"] > cutoff
    e.loc[late, "raw_value"] = [STATES[i] for i in rng.integers(0, 4, late.sum())]
    e.loc[late, "alarm_flag"] = rng.integers(0, 2, late.sum())
    extra = pd.DataFrame({"channel_id": ["a", "b", "c"] * 5,
                          "ts": [cutoff + pd.Timedelta(hours=1 + i) for i in range(15)],
                          "alarm_flag": 1, "raw_value": config.FAULT_LITERAL})
    return pd.concat([e, extra], ignore_index=True)


def _same(a, b):
    return np.allclose(a.values, b.values, equal_nan=True)


def test_intensity_features_ignore_future_events():
    ev = _events(1)
    cutoff = ev["ts"].min() + pd.Timedelta(days=25)
    cand = _cand(ev, cutoff)
    assert _same(fx.intensity_features(cand, ev), fx.intensity_features(cand, _perturb_future(ev, cutoff)))


def test_intensity_decays_with_time_and_counts_recent_events():
    ev = pd.DataFrame({"channel_id": ["a"], "ts": pd.to_datetime(["2024-01-01 00:00:00"]),
                       "alarm_flag": [0], "raw_value": ["Включен"]})
    cand = pd.DataFrame({"channel_id": ["a", "a"], "ts": pd.to_datetime(["2024-01-01 00:00:00", "2024-01-01 01:00:00"])})
    out = fx.intensity_features(cand, ev)
    assert abs(out.loc[0, "int_all_1h"] - 1.0) < 1e-9
    assert abs(out.loc[1, "int_all_1h"] - np.exp(-1.0)) < 1e-6


def test_hourly_baseline_features_ignore_future_events():
    ev = _events(2)
    cutoff = ev["ts"].min() + pd.Timedelta(days=25)
    cand = _cand(ev, cutoff)
    assert _same(fx.hourly_baseline_features(cand, ev), fx.hourly_baseline_features(cand, _perturb_future(ev, cutoff)))


def test_markov_features_use_train_only_matrix_and_ignore_future():
    ev = _events(3)
    train_end = ev["ts"].min() + pd.Timedelta(days=15)
    cutoff = ev["ts"].min() + pd.Timedelta(days=25)
    cand = _cand(ev, cutoff)
    base = fx.markov_features(cand, ev, train_end)
    perturbed = fx.markov_features(cand, _perturb_future(ev, cutoff), train_end)
    assert _same(base, perturbed)


def test_markov_transition_matrix_ignores_events_after_train_end():
    ev = _events(4)
    train_end = ev["ts"].min() + pd.Timedelta(days=15)
    cand = _cand(ev, ev["ts"].min() + pd.Timedelta(days=12))
    base = fx.markov_features(cand, ev, train_end)
    perturbed = fx.markov_features(cand, _perturb_future(ev, train_end), train_end)
    assert _same(base, perturbed)


def test_channel_history_rate_only_uses_labels_older_than_lag():
    rng = np.random.default_rng(6)
    ts = pd.to_datetime("2024-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 40 * 86400, 500)), unit="s")
    cand = pd.DataFrame({"channel_id": rng.choice(["a", "b"], 500), "ts": ts})
    y = (rng.random(500) < 0.3).astype(int)
    base = fx.channel_history_rate(cand, y, lag_hours=72)
    cutoff = pd.Timestamp("2024-01-20")
    y2 = y.copy()
    recent = (cand["ts"] > cutoff - pd.Timedelta(hours=72)).values
    y2[recent] = 1 - y2[recent]
    changed = fx.channel_history_rate(cand, y2, lag_hours=72)
    early = (cand["ts"] <= cutoff).values
    assert np.allclose(base.loc[early].values, changed.loc[early].values)
