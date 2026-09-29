import pandas as pd

from pipeline import alerts as alerts_mod
from pipeline import evaluate as evaluate_mod

LEAD_TIME_BUCKETS_H = [1, 6, 12, 24, 48]


def full_metrics(cand_valid, scores, episodes, horizon_hours, cooldown_hours=24, topk_frac=0.01):
    y_true = cand_valid["target"].values
    ts = cand_valid["ts"].values
    result = dict(evaluate_mod.evaluate(y_true, scores))
    result.update(evaluate_mod.evaluate_daily_topk(ts, y_true, scores))
    result.update(evaluate_mod.evaluate_daily_topk_fixed(ts, y_true, scores))

    df = cand_valid.copy()
    df["_score"] = scores
    valid_start = pd.to_datetime(ts).min()
    valid_end = pd.to_datetime(ts).max()
    n_days = max((valid_end - valid_start).total_seconds() / 86400.0, 1.0)
    episodes_in_period = episodes[
        (episodes["episode_start"] >= valid_start) & (episodes["episode_start"] <= valid_end)
    ]

    raw_topk = alerts_mod.raw_daily_topk(df, "_score", topk_frac, mode="frac")
    alerts_sel = alerts_mod._apply_cooldown(raw_topk, cooldown_hours)
    summary = alerts_mod.alert_summary(alerts_sel, raw_topk, episodes_in_period, horizon_hours, n_days)

    detected, lead_hours = alerts_mod.episode_level_recall(alerts_sel, episodes_in_period, horizon_hours)
    n_ep = len(episodes_in_period)
    for h in LEAD_TIME_BUCKETS_H:
        hit = detected & (lead_hours >= h)
        result[f"episode_recall_lead_ge_{h}h"] = float(hit.sum()) / n_ep if n_ep else None

    result["alert_precision"] = summary["alert_precision"]
    result["alerts_per_day"] = summary["alerts_per_day"]
    result["episode_recall"] = summary["end_to_end_recall"]
    result["median_lead_time_hours"] = summary["median_lead_time_hours"]
    result["p25_lead_time_hours"] = summary["p25_lead_time_hours"]
    result["p75_lead_time_hours"] = summary["p75_lead_time_hours"]
    result["episode_count"] = n_ep
    return result
