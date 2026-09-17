import numpy as np
import pandas as pd
import pytest

from pipeline.sequence.index import EventIndex
from pipeline.sequence.dataset import EventSequenceDataset, balanced_indices
from pipeline.sequence.model import EventTransformer
from pipeline.sequence import train as train_mod
from pipeline.sequence.experiment import build_eval_fn


def _synthetic_events():
    ts = pd.date_range("2022-01-01", periods=50, freq="h")
    return pd.DataFrame({
        "channel_id": ["A"] * 30 + ["B"] * 20,
        "ts": list(ts[:30]) + list(ts[:20]),
        "raw_value": (["Включен", "Выключен"] * 15) + (["Норма", "Неисправен"] * 10),
        "alarm_flag": ([0] * 28 + [1, 1]) + ([0] * 18 + [1, 1]),
    })


def test_window_uses_only_events_at_or_before_t():
    events = _synthetic_events()
    idx = EventIndex(events)
    a_events = events[events["channel_id"] == "A"].reset_index(drop=True)
    cutoff_ts = a_events["ts"].iloc[10]
    cutoff_sec = int(np.datetime64(cutoff_ts).astype("datetime64[s]").astype(np.int64))
    window_ts, window_state, window_alarm, prev_ts = idx.window("A", cutoff_sec, max_len=100)
    future_ts = a_events["ts"].iloc[11:]
    future_sec = future_ts.values.astype("datetime64[s]").astype(np.int64)
    assert window_ts.max() <= cutoff_sec
    assert not np.isin(future_sec, window_ts).any()
    assert len(window_ts) == 11


def test_window_truncates_to_max_len_keeping_most_recent():
    events = _synthetic_events()
    idx = EventIndex(events)
    a_events = events[events["channel_id"] == "A"].reset_index(drop=True)
    cutoff_sec = int(a_events["ts"].iloc[-1].to_datetime64().astype("datetime64[s]").astype(np.int64))
    window_ts, _, _, _ = idx.window("A", cutoff_sec, max_len=5)
    all_a_sec = a_events["ts"].values.astype("datetime64[s]").astype(np.int64)
    assert len(window_ts) == 5
    np.testing.assert_array_equal(window_ts, all_a_sec[-5:])


def test_dataset_padding_mask_matches_real_event_count():
    events = _synthetic_events()
    idx = EventIndex(events)
    a_events = events[events["channel_id"] == "A"].reset_index(drop=True)
    cutoff_ts = a_events["ts"].iloc[4]
    cutoff_sec = int(cutoff_ts.to_datetime64().astype("datetime64[s]").astype(np.int64))
    ds = EventSequenceDataset(idx, ["A"], [cutoff_sec], [0], max_len=20)
    item = ds[0]
    n_real = (~item["pad_mask"].numpy()).sum()
    assert n_real == 5
    assert item["state"].numpy()[item["pad_mask"].numpy()].sum() == 0


def test_dataset_delta_time_matches_manual_computation():
    events = _synthetic_events()
    idx = EventIndex(events)
    b_events = events[events["channel_id"] == "B"].reset_index(drop=True)
    cutoff_ts = b_events["ts"].iloc[9]
    cutoff_sec = int(cutoff_ts.to_datetime64().astype("datetime64[s]").astype(np.int64))
    ds = EventSequenceDataset(idx, ["B"], [cutoff_sec], [0], max_len=20)
    item = ds[0]
    n_real = int((~item["pad_mask"].numpy()).sum())
    deltas = item["delta"].numpy()[-n_real:]
    b_sec = b_events["ts"].values.astype("datetime64[s]").astype(np.int64)[:n_real]
    expected_gaps = np.diff(b_sec, prepend=b_sec[0])
    np.testing.assert_allclose(deltas, np.log1p(expected_gaps), atol=1e-4)


def test_balanced_indices_respects_ratio_and_keeps_all_positives():
    targets = np.array([1, 0, 0, 0, 1, 0, 0, 1, 0, 0])
    idx = balanced_indices(targets, negative_ratio=1.0, seed=1)
    sampled = targets[idx]
    assert sampled.sum() == 3
    assert len(sampled) == 6


def test_model_inference_is_deterministic_in_eval_mode():
    import torch
    torch.manual_seed(0)
    model = EventTransformer(vocab_size=10, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.randint(0, 10, (4, 8))
    alarm = torch.zeros(4, 8)
    delta = torch.zeros(4, 8)
    hour_sin = torch.zeros(4, 8)
    hour_cos = torch.zeros(4, 8)
    pad_mask = torch.zeros(4, 8, dtype=torch.bool)
    with torch.no_grad():
        out1 = model(state, alarm, delta, hour_sin, hour_cos, pad_mask)
        out2 = model(state, alarm, delta, hour_sin, hour_cos, pad_mask)
    torch.testing.assert_close(out1, out2)


def test_model_ignores_padded_positions():
    import torch
    torch.manual_seed(0)
    model = EventTransformer(vocab_size=10, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.zeros(1, 8, dtype=torch.long)
    state[0, -3:] = torch.tensor([2, 3, 4])
    alarm = torch.zeros(1, 8)
    delta = torch.zeros(1, 8)
    hour_sin = torch.zeros(1, 8)
    hour_cos = torch.zeros(1, 8)
    pad_mask = torch.ones(1, 8, dtype=torch.bool)
    pad_mask[0, -3:] = False

    state_noisy = state.clone()
    state_noisy[0, :5] = torch.randint(1, 10, (5,))

    with torch.no_grad():
        out_clean = model(state, alarm, delta, hour_sin, hour_cos, pad_mask)
        out_noisy = model(state_noisy, alarm, delta, hour_sin, hour_cos, pad_mask)
    torch.testing.assert_close(out_clean, out_noisy)


def test_epoch_lr_warmup_then_cosine_decay():
    lrs = [train_mod.epoch_lr(e, 8, 1e-3, warmup_frac=0.1) for e in range(1, 9)]
    assert lrs[0] == pytest.approx(1e-3)
    assert all(b <= a + 1e-12 for a, b in zip(lrs[:-1], lrs[1:]))
    assert lrs[-1] == pytest.approx(0.0, abs=1e-9)


def test_epoch_lr_use_schedule_false_is_truly_constant():
    lrs = [train_mod.epoch_lr(e, 10, 1e-3, warmup_frac=0.0, use_schedule=False) for e in range(1, 11)]
    assert all(v == 1e-3 for v in lrs)
    # sanity: with the schedule ON, warmup_frac=0.0 still decays (this is the bug this test guards against)
    decaying = [train_mod.epoch_lr(e, 10, 1e-3, warmup_frac=0.0, use_schedule=True) for e in range(1, 11)]
    assert decaying[0] < 1e-3
    assert decaying[-1] == pytest.approx(0.0, abs=1e-9)


def _synthetic_candidates(n_channels=5, n=200, seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2020-01-01", periods=200, freq="h")
    events = pd.concat([
        pd.DataFrame({
            "channel_id": f"C{c}", "ts": ts,
            "raw_value": rng.choice(["A", "B", "C"], size=200),
            "alarm_flag": rng.choice([0, 1], size=200, p=[0.9, 0.1]),
        }) for c in range(n_channels)
    ], ignore_index=True)
    idx = EventIndex(events)
    channel_ids = rng.choice([f"C{c}" for c in range(n_channels)], size=n)
    ts_sec = events["ts"].sample(n, replace=True, random_state=seed).values.astype("datetime64[s]").astype(np.int64)
    targets = rng.choice([0, 1], size=n, p=[0.85, 0.15])
    return idx, channel_ids, ts_sec, targets


def test_fit_runs_with_scheduler_and_both_sampling_modes():
    idx, channel_ids, ts_sec, targets = _synthetic_candidates()
    split = 140
    train_ds = EventSequenceDataset(idx, channel_ids[:split], ts_sec[:split], targets[:split], max_len=16)
    valid_ds = EventSequenceDataset(idx, channel_ids[split:], ts_sec[split:], targets[split:], max_len=16)
    valid_ts = ts_sec[split:].astype("datetime64[s]")
    eval_fn = build_eval_fn(valid_ts)

    model = EventTransformer(vocab_size=idx.vocab_size, d_model=16, nhead=2, num_layers=1)
    model, history, device = train_mod.fit(
        model, train_ds, valid_ds, eval_fn, negative_ratio=1.0, batch_size=8, max_epochs=3,
        patience=2, lr=5e-4, warmup_frac=0.1, weight_decay=0.01, use_balanced_sampling=True,
        log_fn=lambda msg: None,
    )
    assert len(history) >= 1
    assert history[0]["lr"] == pytest.approx(5e-4)
    assert all("primary_metric" in h for h in history)

    model2 = EventTransformer(vocab_size=idx.vocab_size, d_model=16, nhead=2, num_layers=1)
    model2, history2, device2 = train_mod.fit(
        model2, train_ds, valid_ds, eval_fn, batch_size=8, max_epochs=2, patience=2,
        lr=5e-4, warmup_frac=0.0, use_balanced_sampling=False, pos_weight=5.0,
        log_fn=lambda msg: None,
    )
    assert len(history2) >= 1


def test_checkpoint_selection_prefers_primary_metric_with_ap_tiebreak():
    idx, channel_ids, ts_sec, targets = _synthetic_candidates(seed=1)
    split = 140
    train_ds = EventSequenceDataset(idx, channel_ids[:split], ts_sec[:split], targets[:split], max_len=16)
    valid_ds = EventSequenceDataset(idx, channel_ids[split:], ts_sec[split:], targets[split:], max_len=16)

    import torch as _torch

    calls = {"i": 0}
    snapshots = {}
    scripted = [
        {"primary_metric": 0.5, "avg_precision": 0.3},
        {"primary_metric": 0.5, "avg_precision": 0.6},
        {"primary_metric": 0.2, "avg_precision": 0.9},
    ]

    def scripted_eval_fn(y_true, y_score):
        i = calls["i"]
        calls["i"] += 1
        return dict(scripted[i])

    model = EventTransformer(vocab_size=idx.vocab_size, d_model=16, nhead=2, num_layers=1)
    orig_fit_loader_step = model.state_dict

    def snapshotting_state_dict(*args, **kwargs):
        sd = orig_fit_loader_step(*args, **kwargs)
        snapshots[calls["i"]] = {k: v.clone() for k, v in sd.items()}
        return sd

    model.state_dict = snapshotting_state_dict
    _, history, _ = train_mod.fit(
        model, train_ds, valid_ds, scripted_eval_fn, batch_size=8, max_epochs=3, patience=5,
        lr=1e-4, log_fn=lambda msg: None,
    )
    assert len(history) == 3
    # epoch2 has equal primary_metric to epoch1 but higher avg_precision -> wins the tiebreak;
    # epoch3 has a lower primary_metric than the running best, so it is never checkpointed.
    assert set(snapshots.keys()) == {1, 2}
    final_state = model.state_dict()
    for k, v in final_state.items():
        _torch.testing.assert_close(v, snapshots[2][k])
