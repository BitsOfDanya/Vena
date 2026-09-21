import numpy as np
import torch
from torch.utils.data import Dataset


class EventSequenceDataset(Dataset):
    def __init__(self, event_index, channel_ids, ts_sec, targets, max_len):
        self.index = event_index
        self.channel_ids = np.asarray(channel_ids).astype(str)
        self.ts_sec = np.asarray(ts_sec, dtype=np.int64)
        self.targets = np.asarray(targets, dtype=np.float32)
        self.max_len = max_len

    def __len__(self):
        return len(self.ts_sec)

    def __getitem__(self, i):
        cid = self.channel_ids[i]
        t = self.ts_sec[i]
        window_ts, window_state, window_alarm, prev_ts = self.index.window(cid, t, self.max_len)
        n = len(window_ts)
        pad = self.max_len - n

        state_arr = np.zeros(self.max_len, dtype=np.int64)
        alarm_arr = np.zeros(self.max_len, dtype=np.float32)
        delta_arr = np.zeros(self.max_len, dtype=np.float32)
        hour_sin = np.zeros(self.max_len, dtype=np.float32)
        hour_cos = np.zeros(self.max_len, dtype=np.float32)
        pad_mask = np.ones(self.max_len, dtype=bool)

        if n > 0:
            state_arr[pad:] = window_state.astype(np.int64) + 1
            alarm_arr[pad:] = window_alarm.astype(np.float32)
            first_prev = prev_ts if prev_ts is not None else window_ts[0]
            prev_seq = np.concatenate([[first_prev], window_ts[:-1]])
            delta_sec = np.maximum(window_ts - prev_seq, 0).astype(np.float64)
            delta_arr[pad:] = np.log1p(delta_sec).astype(np.float32)
            hours = (window_ts % 86400) / 3600.0
            hour_sin[pad:] = np.sin(2 * np.pi * hours / 24.0)
            hour_cos[pad:] = np.cos(2 * np.pi * hours / 24.0)
            pad_mask[pad:] = False

        return {
            "state": torch.from_numpy(state_arr),
            "alarm": torch.from_numpy(alarm_arr),
            "delta": torch.from_numpy(delta_arr),
            "hour_sin": torch.from_numpy(hour_sin),
            "hour_cos": torch.from_numpy(hour_cos),
            "pad_mask": torch.from_numpy(pad_mask),
            "target": torch.tensor(self.targets[i], dtype=torch.float32),
        }


def balanced_indices(targets, negative_ratio, seed):
    targets = np.asarray(targets)
    pos_idx = np.where(targets == 1)[0]
    neg_idx = np.where(targets == 0)[0]
    rng = np.random.default_rng(seed)
    n_neg = min(len(neg_idx), int(len(pos_idx) * negative_ratio))
    sampled_neg = rng.choice(neg_idx, size=n_neg, replace=False)
    combined = np.concatenate([pos_idx, sampled_neg])
    rng.shuffle(combined)
    return combined
