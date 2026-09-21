import numpy as np
import pandas as pd

from pipeline import alerts as alerts_mod
from pipeline.formal import metrics as fm


def operating_point_report(frame, threshold, episodes, horizon_hours, cooldown_hours=24):
    y = frame["target"].values
    score = frame["score"].values
    cand = fm.eval_at_threshold(y, score, threshold)
    selected = frame.loc[score >= threshold, ["channel_id", "ts", "target"]]
    alerts = alerts_mod._apply_cooldown(selected, cooldown_hours)
    start, end = pd.to_datetime(frame["ts"]).min(), pd.to_datetime(frame["ts"]).max()
    eps = episodes[(episodes["episode_start"] >= start) & (episodes["episode_start"] <= end)]
    n_days = max((end - start).total_seconds() / 86400.0, 1.0)
    summary = alerts_mod.alert_summary(alerts, selected, eps, horizon_hours, n_days)
    return {
        "candidate_precision": cand["precision"], "candidate_recall": cand["recall"],
        "n_candidates_selected": int(len(selected)), "n_alerts_dedup": int(summary["n_alerts"]),
        "alert_precision_dedup": summary["alert_precision"], "episode_recall": summary["end_to_end_recall"],
        "alerts_per_day": summary["alerts_per_day"], "median_lead_time_hours": summary["median_lead_time_hours"],
        "episodes": int(summary["failure_episodes_total"]),
    }


def previous_fold_threshold(prev_frame, target_precision):
    y = prev_frame["target"].values
    s = prev_frame["score"].values
    order = np.argsort(-s)
    tp = np.cumsum(y[order])
    prec = tp / np.arange(1, len(s) + 1)
    ok = np.flatnonzero(prec >= target_precision)
    if len(ok) == 0:
        return float("inf")
    return float(s[order][ok[-1]])
