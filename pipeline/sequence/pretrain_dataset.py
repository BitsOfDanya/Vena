import numpy as np
import torch
from torch.utils.data import Dataset


def sample_pretrain_anchors(event_index, cutoff_sec, max_per_channel, seed, min_context=2):
    rng = np.random.default_rng(seed)
    out_channels = []
    out_ts = []
    for cid, (start, end) in event_index.channel_ranges.items():
        ts_slice = event_index.ts_sec[start:end]
        n_eligible = int(np.searchsorted(ts_slice, cutoff_sec, side="right"))
        if n_eligible < min_context:
            continue
        positions = np.arange(min_context - 1, n_eligible)
        if len(positions) > max_per_channel:
            positions = rng.choice(positions, size=max_per_channel, replace=False)
        out_channels.extend([cid] * len(positions))
        out_ts.extend(ts_slice[positions].tolist())
    return np.array(out_channels), np.array(out_ts, dtype=np.int64)


class PretrainSequenceDataset(Dataset):
    def __init__(self, event_index, channel_ids, ts_sec, max_len, mask_token_id, mask_prob=0.15, seed=0):
        self.index = event_index
        self.channel_ids = np.asarray(channel_ids).astype(str)
        self.ts_sec = np.asarray(ts_sec, dtype=np.int64)
        self.max_len = max_len
        self.mask_token_id = mask_token_id
        self.mask_prob = mask_prob
        self.seed = seed

    def __len__(self):
        return len(self.ts_sec)

    def __getitem__(self, i):
        # Right-padded (real content first, PAD at the end): required for the causal
        # next-event branch, where left-padding would leave leading PAD positions with
        # zero valid attention keys under causal + key-padding masking (all -inf row -> NaN).
        # Bidirectional masked-LM is padding-side agnostic, so the same layout is reused.
        cid = self.channel_ids[i]
        t = self.ts_sec[i]
        window_ts, window_state, window_alarm, prev_ts = self.index.window(cid, t, self.max_len)
        n = len(window_ts)

        state_arr = np.zeros(self.max_len, dtype=np.int64)
        alarm_arr = np.zeros(self.max_len, dtype=np.float32)
        delta_arr = np.zeros(self.max_len, dtype=np.float32)
        hour_sin = np.zeros(self.max_len, dtype=np.float32)
        hour_cos = np.zeros(self.max_len, dtype=np.float32)
        pad_mask = np.ones(self.max_len, dtype=bool)

        if n > 0:
            state_arr[:n] = window_state.astype(np.int64) + 1
            alarm_arr[:n] = window_alarm.astype(np.float32)
            first_prev = prev_ts if prev_ts is not None else window_ts[0]
            prev_seq = np.concatenate([[first_prev], window_ts[:-1]])
            delta_sec = np.maximum(window_ts - prev_seq, 0).astype(np.float64)
            delta_arr[:n] = np.log1p(delta_sec).astype(np.float32)
            hours = (window_ts % 86400) / 3600.0
            hour_sin[:n] = np.sin(2 * np.pi * hours / 24.0)
            hour_cos[:n] = np.cos(2 * np.pi * hours / 24.0)
            pad_mask[:n] = False

        rng = np.random.default_rng(self.seed * 1_000_003 + i)

        mask_input = state_arr.copy()
        mask_labels = np.full(self.max_len, -100, dtype=np.int64)
        real_idx = np.where(~pad_mask)[0]
        if len(real_idx) > 0:
            n_to_mask = max(1, int(round(len(real_idx) * self.mask_prob)))
            masked_positions = rng.choice(real_idx, size=min(n_to_mask, len(real_idx)), replace=False)
            mask_labels[masked_positions] = state_arr[masked_positions]
            mask_input[masked_positions] = self.mask_token_id

        next_labels = np.full(self.max_len, -100, dtype=np.int64)
        if len(real_idx) >= 2:
            for pos, nxt in zip(real_idx[:-1], real_idx[1:]):
                next_labels[pos] = state_arr[nxt]

        return {
            "state_masked": torch.from_numpy(mask_input),
            "mask_labels": torch.from_numpy(mask_labels),
            "state_orig": torch.from_numpy(state_arr),
            "next_labels": torch.from_numpy(next_labels),
            "alarm": torch.from_numpy(alarm_arr),
            "delta": torch.from_numpy(delta_arr),
            "hour_sin": torch.from_numpy(hour_sin),
            "hour_cos": torch.from_numpy(hour_cos),
            "pad_mask": torch.from_numpy(pad_mask),
        }
