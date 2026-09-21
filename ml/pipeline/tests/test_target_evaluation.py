import numpy as np
import pandas as pd

from pipeline.targets import evaluation


def _frame():
    t0 = pd.Timestamp("2024-01-01")
    rows = []
    for i in range(10):
        rows.append(("a", t0 + pd.Timedelta(hours=i), 1 if i >= 4 else 0, 0.9 if i >= 4 else 0.1))
    for i in range(10):
        rows.append(("b", t0 + pd.Timedelta(hours=i), 0, 0.2))
    return pd.DataFrame(rows, columns=["channel_id", "ts", "target", "score"])


def test_operating_point_reports_dedup_alerts_and_episode_recall():
    eps = pd.DataFrame({"channel_id": ["a"], "episode_start": [pd.Timestamp("2024-01-01 08:30")],
                        "episode_end": [pd.Timestamp("2024-01-01 08:40")]})
    out = evaluation.operating_point_report(_frame(), 0.5, eps, 24, cooldown_hours=24)
    assert out["candidate_precision"] == 1.0 and out["candidate_recall"] == 1.0
    assert out["n_candidates_selected"] == 6
    assert out["n_alerts_dedup"] == 1
    assert out["episode_recall"] == 1.0


def test_previous_fold_threshold_uses_only_given_scores_and_hits_target_precision():
    prev = _frame()
    thr = evaluation.previous_fold_threshold(prev, 0.9)
    sel = prev[prev["score"] >= thr]
    assert sel["target"].mean() >= 0.9
    assert evaluation.previous_fold_threshold(prev.assign(target=0), 0.5) == float("inf")


def test_train_and_report_saves_model_and_refuses_lockbox_years(tmp_path):
    import json
    import pytest
    from pipeline.targets import modules

    rng = np.random.default_rng(0)
    n = 6000
    ts = pd.to_datetime("2023-01-01") + pd.to_timedelta(np.sort(rng.integers(0, 3 * 365 * 86400, n)), unit="s")
    frame = pd.DataFrame({"ts": ts, "f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    frame["y"] = (frame["f1"] + 0.3 * rng.normal(size=n) > 0.4).astype(int)
    report = modules.train_and_report(frame, "y", ["f1", "f2"], 2024, 2025, str(tmp_path), "demo", model_params={"n_jobs": 1})
    assert (tmp_path / "demo.joblib").exists()
    assert json.load(open(tmp_path / "demo_report.json"))["valid_year"] == 2025
    assert report["pr_auc"] > report["base_rate"]
    with pytest.raises(ValueError):
        modules.train_and_report(frame, "y", ["f1", "f2"], 2024, 2026, str(tmp_path), "demo")
