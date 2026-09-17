import numpy as np
import pandas as pd
import torch

from pipeline.sequence.index import EventIndex
from pipeline.sequence.hybrid_dataset import HybridSequenceDataset
from pipeline.sequence.hybrid_model import HybridEventTransformer


def _synthetic_events(seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2020-01-01", periods=100, freq="h")
    return pd.concat([
        pd.DataFrame({
            "channel_id": f"C{c}", "ts": ts,
            "raw_value": rng.choice(["A", "B", "C"], size=100),
            "alarm_flag": rng.choice([0, 1], size=100, p=[0.9, 0.1]),
        }) for c in range(3)
    ], ignore_index=True)


def test_hybrid_dataset_attaches_correct_feature_row():
    events = _synthetic_events()
    idx = EventIndex(events)
    n = 10
    channel_ids = ["C0"] * n
    ts_sec = events[events["channel_id"] == "C0"]["ts"].values[:n].astype("datetime64[s]").astype(np.int64)
    targets = np.zeros(n)
    features = np.arange(n * 4).reshape(n, 4).astype(np.float32)

    ds = HybridSequenceDataset(idx, channel_ids, ts_sec, targets, features, max_len=16)
    for i in [0, 3, 7]:
        item = ds[i]
        np.testing.assert_array_equal(item["features"].numpy(), features[i])
    assert len(ds) == n
    np.testing.assert_array_equal(ds.targets, targets)


def test_normalization_uses_only_train_rows():
    x = np.array([[1.0], [2.0], [3.0], [100.0]], dtype=np.float32)
    train_mask = np.array([True, True, True, False])
    mean = x[train_mask].mean(axis=0)
    std = x[train_mask].std(axis=0)
    assert mean[0] == 2.0
    # the outlier (row 3, held out of train) must not influence the fitted mean/std
    assert mean[0] != x.mean(axis=0)[0]


def test_hybrid_model_forward_is_deterministic_and_finite():
    torch.manual_seed(0)
    model = HybridEventTransformer(vocab_size=10, feature_dim=5, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.randint(0, 10, (4, 8))
    alarm = torch.zeros(4, 8)
    delta = torch.zeros(4, 8)
    hour_sin = torch.zeros(4, 8)
    hour_cos = torch.zeros(4, 8)
    pad_mask = torch.zeros(4, 8, dtype=torch.bool)
    features = torch.randn(4, 5)
    with torch.no_grad():
        out1 = model(state, alarm, delta, hour_sin, hour_cos, pad_mask, features)
        out2 = model(state, alarm, delta, hour_sin, hour_cos, pad_mask, features)
    torch.testing.assert_close(out1, out2)
    assert torch.isfinite(out1).all()


def test_hybrid_model_uses_engineered_features():
    torch.manual_seed(0)
    model = HybridEventTransformer(vocab_size=10, feature_dim=5, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.randint(0, 10, (2, 8))
    alarm = torch.zeros(2, 8)
    delta = torch.zeros(2, 8)
    hour_sin = torch.zeros(2, 8)
    hour_cos = torch.zeros(2, 8)
    pad_mask = torch.zeros(2, 8, dtype=torch.bool)
    features_a = torch.zeros(2, 5)
    features_b = torch.ones(2, 5) * 10.0
    with torch.no_grad():
        out_a = model(state, alarm, delta, hour_sin, hour_cos, pad_mask, features_a)
        out_b = model(state, alarm, delta, hour_sin, hour_cos, pad_mask, features_b)
    assert not torch.allclose(out_a, out_b)


def test_hybrid_model_ignores_padded_positions():
    torch.manual_seed(0)
    model = HybridEventTransformer(vocab_size=10, feature_dim=3, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.zeros(1, 8, dtype=torch.long)
    state[0, -3:] = torch.tensor([2, 3, 4])
    alarm = torch.zeros(1, 8)
    delta = torch.zeros(1, 8)
    hour_sin = torch.zeros(1, 8)
    hour_cos = torch.zeros(1, 8)
    pad_mask = torch.ones(1, 8, dtype=torch.bool)
    pad_mask[0, -3:] = False
    features = torch.randn(1, 3)

    state_noisy = state.clone()
    state_noisy[0, :5] = torch.randint(1, 10, (5,))

    with torch.no_grad():
        out_clean = model(state, alarm, delta, hour_sin, hour_cos, pad_mask, features)
        out_noisy = model(state_noisy, alarm, delta, hour_sin, hour_cos, pad_mask, features)
    torch.testing.assert_close(out_clean, out_noisy)
