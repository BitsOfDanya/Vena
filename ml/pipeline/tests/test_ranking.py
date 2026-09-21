import numpy as np
import torch
import torch.nn.functional as F

from pipeline.sequence.ranking import build_day_index, sample_ranking_batch, pairwise_ranking_loss


def test_build_day_index_only_keeps_days_with_both_classes():
    ts_sec = np.array([0, 1000, 86400, 86400 + 1000, 2 * 86400, 2 * 86400 + 500])
    targets = np.array([1, 1, 1, 0, 0, 0])
    day_to_idx, eligible_days = build_day_index(ts_sec, targets)
    assert len(day_to_idx) == 3
    assert 0 not in eligible_days
    assert 2 not in eligible_days
    assert 1 in eligible_days


def test_sample_ranking_batch_never_mixes_days_within_a_boundary_group():
    rng = np.random.default_rng(0)
    n_days = 5
    ts_sec = []
    targets = []
    for d in range(n_days):
        ts_sec += [d * 86400 + 100, d * 86400 + 200, d * 86400 + 300]
        targets += [1, 0, 0]
    ts_sec = np.array(ts_sec)
    targets = np.array(targets)
    day_to_idx, eligible_days = build_day_index(ts_sec, targets)

    batch_idx, boundaries = sample_ranking_batch(day_to_idx, eligible_days, targets,
                                                   max_days=3, max_per_day=10, rng=rng)
    days_of_rows = ts_sec[batch_idx] // 86400
    for start, end in boundaries:
        group_days = days_of_rows[start:end]
        assert len(set(group_days.tolist())) == 1, "a single boundary group must come from one calendar day"


def test_pairwise_ranking_loss_ignores_cross_day_comparisons():
    scores = torch.tensor([-5.0, 5.0, 100.0, -100.0])  # A-pos, A-neg, B-pos, B-neg
    targets = torch.tensor([1.0, 0.0, 1.0, 0.0])
    boundaries = [(0, 2), (2, 4)]
    loss = pairwise_ranking_loss(scores, targets, boundaries, F.logsigmoid)

    loss_a = -F.logsigmoid(scores[0] - scores[1])  # A: pos(-5) vs neg(5), bad ordering
    loss_b = -F.logsigmoid(scores[2] - scores[3])  # B: pos(100) vs neg(-100), good ordering
    expected = (loss_a + loss_b) / 2  # 1 pair per day, equal weight
    torch.testing.assert_close(loss, expected)


def test_pairwise_ranking_loss_rewards_correct_within_day_ordering():
    targets = torch.tensor([1.0, 0.0])
    boundaries = [(0, 2)]
    good = pairwise_ranking_loss(torch.tensor([5.0, -5.0]), targets, boundaries, F.logsigmoid)
    bad = pairwise_ranking_loss(torch.tensor([-5.0, 5.0]), targets, boundaries, F.logsigmoid)
    assert good.item() < bad.item()


def test_pairwise_ranking_loss_returns_none_without_eligible_days():
    targets = torch.tensor([1.0, 1.0])
    loss = pairwise_ranking_loss(torch.tensor([1.0, 2.0]), targets, [(0, 2)], F.logsigmoid)
    assert loss is None
