import numpy as np
import torch

from pipeline.sequence.hybrid_dataset import HybridSequenceDataset


class DistillHybridSequenceDataset(HybridSequenceDataset):
    def __init__(self, event_index, channel_ids, ts_sec, targets, features, teacher_probs, max_len):
        super().__init__(event_index, channel_ids, ts_sec, targets, features, max_len)
        self.teacher_probs = np.asarray(teacher_probs, dtype=np.float32)

    def __getitem__(self, i):
        item = super().__getitem__(i)
        item["teacher"] = torch.tensor(self.teacher_probs[i], dtype=torch.float32)
        return item
