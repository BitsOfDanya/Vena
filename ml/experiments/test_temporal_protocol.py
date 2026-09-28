"""Boundary checks for the temporal experiment protocol."""

import numpy as np
import pandas as pd
import pytest

from experiments.audit_adaptive_online_fan import prior_score_thresholds
from experiments.common import threshold_at_precision, validation_mask
from experiments.run_recency_experiment import select_training_rows, variant_weights


def test_trailing_window_keeps_embargo_before_validation():
    """Training labels must end before the 168-hour future window."""
    frame = pd.DataFrame({
        "ts": pd.to_datetime([
            "2020-06-01 00:00:00", "2021-01-01 00:00:00",
            "2023-12-24 23:59:59", "2023-12-25 00:00:00",
            "2024-01-01 00:00:00",
        ]),
    })
    mask = select_training_rows(frame, 2024, "recent_3y", 168)
    assert mask.tolist() == [False, True, True, False, False]


def test_lockbox_drops_rows_without_full_future_horizon():
    """The final 72 hours of the available 2026 journal are censored."""
    frame = pd.DataFrame({
        "ts": pd.to_datetime([
            "2025-12-31", "2026-06-27", "2026-06-28", "2026-06-30",
        ]),
    })
    assert validation_mask(frame, 2026).tolist() == [False, True, False, False]


def test_near_negative_weighting_requires_label_embargo():
    """A near-future training label cannot cross into the validation year."""
    frame = pd.DataFrame({
        "ts": pd.to_datetime(["2023-06-01", "2023-06-02", "2024-01-01"]),
        "target": [0, 1, 0],
        "y168": [1, 1, 1],
    })
    train = np.array([True, True, False])
    with pytest.raises(ValueError):
        variant_weights(frame, train, "recent_3y_near_4", 2024, 72)
    assert variant_weights(frame, train, "recent_3y_near_4", 2024, 168).tolist() == [4, 1]


def test_threshold_requires_precision_strictly_above_target():
    """Equality at 0.70 must not be selected for a strict target."""
    labels = np.array([1] * 7 + [0] * 3)
    scores = np.ones(len(labels))
    assert threshold_at_precision(labels, scores, 0.70) is None


def test_online_quantile_uses_only_prior_days():
    """A future score cannot change a previously emitted threshold."""
    early = np.full(500, np.datetime64("2025-01-01"))
    times = np.concatenate([early, [np.datetime64("2025-01-02")]])
    scores = np.concatenate([np.linspace(0, 1, 500), [0.2]])
    before = prior_score_thresholds(times, scores, 0.9, 30)
    after = prior_score_thresholds(
        np.concatenate([times, [np.datetime64("2025-01-03")]]),
        np.concatenate([scores, [100.0]]), 0.9, 30,
    )
    np.testing.assert_allclose(before, after[:-1])
    assert before[-1] == np.quantile(scores[:-1], 0.95)
