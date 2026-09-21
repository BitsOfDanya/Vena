import numpy as np


def build_day_index(ts_sec, targets):
    days = np.asarray(ts_sec, dtype=np.int64) // 86400
    day_to_idx = {}
    for i, d in enumerate(days):
        day_to_idx.setdefault(int(d), []).append(i)
    eligible_days = [
        d for d, idx in day_to_idx.items()
        if any(targets[i] == 1 for i in idx) and any(targets[i] == 0 for i in idx)
    ]
    return day_to_idx, eligible_days


def sample_ranking_batch(day_to_idx, eligible_days, targets, max_days, max_per_day, rng):
    if not eligible_days:
        return np.array([], dtype=np.int64), []
    n_days = min(max_days, len(eligible_days))
    chosen_days = rng.choice(eligible_days, size=n_days, replace=False)

    batch_idx = []
    day_boundaries = []
    for d in chosen_days:
        idx = np.array(day_to_idx[d])
        pos = idx[targets[idx] == 1]
        neg = idx[targets[idx] == 0]
        if len(neg) > max_per_day - len(pos):
            n_neg_keep = max(max_per_day - len(pos), 1)
            neg = rng.choice(neg, size=min(n_neg_keep, len(neg)), replace=False)
        day_rows = np.concatenate([pos, neg])
        start = len(batch_idx)
        batch_idx.extend(day_rows.tolist())
        day_boundaries.append((start, len(batch_idx)))
    return np.array(batch_idx, dtype=np.int64), day_boundaries


def pairwise_ranking_loss(scores, targets, day_boundaries, logsigmoid_fn):
    total = None
    n_pairs = 0
    for start, end in day_boundaries:
        day_targets = targets[start:end]
        day_scores = scores[start:end]
        pos_mask = day_targets == 1
        neg_mask = day_targets == 0
        pos_scores = day_scores[pos_mask]
        neg_scores = day_scores[neg_mask]
        if pos_scores.numel() == 0 or neg_scores.numel() == 0:
            continue
        diff = pos_scores.unsqueeze(1) - neg_scores.unsqueeze(0)
        day_loss = (-logsigmoid_fn(diff)).sum()
        total = day_loss if total is None else total + day_loss
        n_pairs += pos_scores.numel() * neg_scores.numel()
    if total is None or n_pairs == 0:
        return None
    return total / n_pairs
