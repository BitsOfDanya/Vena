import numpy as np
import pandas as pd
import torch

from pipeline.sequence.index import EventIndex
from pipeline.sequence.pretrain_dataset import sample_pretrain_anchors, PretrainSequenceDataset
from pipeline.sequence.model import EventPretrainModel, EventTransformer


def _synthetic_events_with_future(seed=0):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2019-01-01", periods=400, freq="6h")
    events = pd.concat([
        pd.DataFrame({
            "channel_id": f"C{c}", "ts": ts,
            "raw_value": rng.choice(["A", "B", "C", "D"], size=400),
            "alarm_flag": rng.choice([0, 1], size=400, p=[0.92, 0.08]),
        }) for c in range(4)
    ], ignore_index=True)
    return events


def test_pretrain_anchors_never_exceed_cutoff():
    events = _synthetic_events_with_future()
    idx = EventIndex(events)
    cutoff = pd.Timestamp("2019-04-01")
    cutoff_sec = int(cutoff.timestamp())
    channels, anchors_ts = sample_pretrain_anchors(idx, cutoff_sec, max_per_channel=50, seed=1)
    assert len(anchors_ts) > 0
    assert (anchors_ts <= cutoff_sec).all()


def test_pretrain_windows_never_contain_future_events():
    events = _synthetic_events_with_future()
    idx = EventIndex(events)
    cutoff = pd.Timestamp("2019-04-01")
    cutoff_sec = int(cutoff.timestamp())
    channels, anchors_ts = sample_pretrain_anchors(idx, cutoff_sec, max_per_channel=50, seed=1)
    for cid, t in zip(channels[:100], anchors_ts[:100]):
        window_ts, _, _, _ = idx.window(cid, t, max_len=32)
        assert (window_ts <= cutoff_sec).all()


def test_pretrain_dataset_uses_right_padding():
    events = _synthetic_events_with_future()
    idx = EventIndex(events)
    cutoff_sec = int(pd.Timestamp("2019-04-01").timestamp())
    channels, anchors_ts = sample_pretrain_anchors(idx, cutoff_sec, max_per_channel=20, seed=2)
    ds = PretrainSequenceDataset(idx, channels, anchors_ts, max_len=16, mask_token_id=99, mask_prob=0.0, seed=4)
    item = ds[0]
    real = (~item["pad_mask"].numpy()).astype(int)
    n_real = real.sum()
    assert n_real > 0
    np.testing.assert_array_equal(real, np.array([1] * n_real + [0] * (16 - n_real)))


def test_masked_lm_target_matches_original_state_at_masked_positions():
    events = _synthetic_events_with_future()
    idx = EventIndex(events)
    cutoff_sec = int(pd.Timestamp("2019-04-01").timestamp())
    channels, anchors_ts = sample_pretrain_anchors(idx, cutoff_sec, max_per_channel=20, seed=2)
    ds = PretrainSequenceDataset(idx, channels, anchors_ts, max_len=16, mask_token_id=99, mask_prob=0.3, seed=5)
    item = ds[0]
    masked_positions = (item["mask_labels"].numpy() != -100)
    assert masked_positions.sum() > 0
    assert (item["state_masked"].numpy()[masked_positions] == 99).all()
    np.testing.assert_array_equal(
        item["mask_labels"].numpy()[masked_positions],
        item["state_orig"].numpy()[masked_positions],
    )
    unmasked_real = (~masked_positions) & (~item["pad_mask"].numpy())
    np.testing.assert_array_equal(
        item["state_masked"].numpy()[unmasked_real],
        item["state_orig"].numpy()[unmasked_real],
    )


def test_next_event_target_matches_following_real_position():
    events = _synthetic_events_with_future()
    idx = EventIndex(events)
    cutoff_sec = int(pd.Timestamp("2019-04-01").timestamp())
    channels, anchors_ts = sample_pretrain_anchors(idx, cutoff_sec, max_per_channel=20, seed=3)
    ds = PretrainSequenceDataset(idx, channels, anchors_ts, max_len=16, mask_token_id=99, mask_prob=0.0, seed=7)
    item = ds[0]
    state = item["state_orig"].numpy()
    next_labels = item["next_labels"].numpy()
    pad_mask = item["pad_mask"].numpy()
    real_idx = np.where(~pad_mask)[0]
    for pos, nxt in zip(real_idx[:-1], real_idx[1:]):
        assert next_labels[pos] == state[nxt]
    assert next_labels[real_idx[-1]] == -100
    assert (next_labels[pad_mask] == -100).all()


def test_pretrain_model_causal_forward_is_finite_with_padding():
    torch.manual_seed(0)
    model = EventPretrainModel(vocab_size=10, d_model=16, nhead=2, num_layers=2)
    model.eval()
    state = torch.zeros(3, 8, dtype=torch.long)
    state[:, :3] = torch.randint(1, 9, (3, 3))
    pad_mask = torch.ones(3, 8, dtype=torch.bool)
    pad_mask[:, :3] = False
    alarm = torch.zeros(3, 8)
    delta = torch.zeros(3, 8)
    hour_sin = torch.zeros(3, 8)
    hour_cos = torch.zeros(3, 8)
    with torch.no_grad():
        out = model.forward_next(state, alarm, delta, hour_sin, hour_cos, pad_mask)
    assert torch.isfinite(out).all()


def test_pretrain_model_next_head_is_causal():
    torch.manual_seed(0)
    model = EventPretrainModel(vocab_size=10, d_model=16, nhead=2, num_layers=1)
    model.eval()
    state = torch.randint(1, 9, (2, 6))
    alarm = torch.zeros(2, 6)
    delta = torch.zeros(2, 6)
    hour_sin = torch.zeros(2, 6)
    hour_cos = torch.zeros(2, 6)
    pad_mask = torch.zeros(2, 6, dtype=torch.bool)

    state_perturbed = state.clone()
    state_perturbed[:, -1] = torch.randint(1, 9, (2,))

    with torch.no_grad():
        out_orig = model.forward_next(state, alarm, delta, hour_sin, hour_cos, pad_mask)
        out_perturbed = model.forward_next(state_perturbed, alarm, delta, hour_sin, hour_cos, pad_mask)
    torch.testing.assert_close(out_orig[:, :-1], out_perturbed[:, :-1])


def test_load_pretrained_encoder_transfers_weights():
    torch.manual_seed(0)
    pretrain_model = EventPretrainModel(vocab_size=11, d_model=16, nhead=2, num_layers=1)
    classifier = EventTransformer(vocab_size=11, d_model=16, nhead=2, num_layers=1)
    classifier.load_pretrained_encoder(pretrain_model)
    for p1, p2 in zip(classifier.tokenizer.parameters(), pretrain_model.tokenizer.parameters()):
        torch.testing.assert_close(p1, p2)
    for p1, p2 in zip(classifier.encoder.parameters(), pretrain_model.encoder.parameters()):
        torch.testing.assert_close(p1, p2)
