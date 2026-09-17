import numpy as np
import torch
from torch.utils.data import Dataset

from pipeline.sequence.dataset import EventSequenceDataset


class HybridSequenceDataset(Dataset):
    def __init__(self, event_index, channel_ids, ts_sec, targets, features, max_len):
        self.seq_ds = EventSequenceDataset(event_index, channel_ids, ts_sec, targets, max_len)
        self.features = np.asarray(features, dtype=np.float32)

    def __len__(self):
        return len(self.seq_ds)

    @property
    def targets(self):
        return self.seq_ds.targets

    def __getitem__(self, i):
        item = self.seq_ds[i]
        item["features"] = torch.from_numpy(self.features[i])
        return item
