import numpy as np
import pandas as pd


def candidate_coverage(candidates, episodes, horizon_hours):
    horizon = np.timedelta64(int(horizon_hours), "h")
    if episodes.empty:
        return np.array([], dtype=bool)
    cand_by_channel = {
        cid: np.sort(g["ts"].values) for cid, g in candidates.groupby("channel_id", observed=True)
    } if len(candidates) else {}
    starts = episodes["episode_start"].values
    channels = episodes["channel_id"].values
    covered = np.zeros(len(episodes), dtype=bool)
    for i in range(len(episodes)):
        cts = cand_by_channel.get(channels[i])
        if cts is None or len(cts) == 0:
            continue
        t = starts[i]
        lo = np.searchsorted(cts, t - horizon, side="left")
        hi = np.searchsorted(cts, t, side="left")
        covered[i] = hi > lo
    return covered


def _apply_cooldown(points, cooldown_hours):
    if points.empty:
        return points
    cooldown = pd.Timedelta(hours=cooldown_hours)
    ordered = points.sort_values(["channel_id", "ts"])
    keep_mask = np.ones(len(ordered), dtype=bool)
    last_alert = {}
    channel_vals = ordered["channel_id"].values
    ts_vals = ordered["ts"].values
    for i in range(len(ordered)):
        cid = channel_vals[i]
        t = ts_vals[i]
        prev = last_alert.get(cid)
        if prev is not None and (t - prev) < np.timedelta64(cooldown):
            keep_mask[i] = False
        else:
            last_alert[cid] = t
    return ordered.loc[keep_mask]


def select_alerts_by_threshold(df, score_col, threshold, cooldown_hours):
    raw = df[df[score_col] >= threshold]
    return _apply_cooldown(raw, cooldown_hours)


def raw_daily_topk(df, score_col, k, mode="frac"):
    d = df.copy()
    d["_day"] = pd.to_datetime(d["ts"]).dt.floor("D")
    parts = []
    for _, g in d.groupby("_day"):
        if mode == "frac":
            n_top = max(int(len(g) * k), 1)
        else:
            n_top = int(k)
        parts.append(g.nlargest(n_top, score_col))
    raw = pd.concat(parts, ignore_index=False) if parts else d.iloc[0:0]
    return raw.drop(columns=["_day"])


def select_alerts_by_daily_topk(df, score_col, k, cooldown_hours, mode="frac"):
    raw = raw_daily_topk(df, score_col, k, mode=mode)
    return _apply_cooldown(raw, cooldown_hours)


def episode_level_recall(alerts, episodes, horizon_hours):
    horizon = np.timedelta64(int(horizon_hours), "h")
    n = len(episodes)
    detected = np.zeros(n, dtype=bool)
    lead_time_hours = np.full(n, np.nan)
    if n == 0:
        return detected, lead_time_hours
    alerts_by_channel = {
        cid: np.sort(g["ts"].values) for cid, g in alerts.groupby("channel_id", observed=True)
    } if len(alerts) else {}
    starts = episodes["episode_start"].values
    channels = episodes["channel_id"].values
    for i in range(n):
        a_ts = alerts_by_channel.get(channels[i])
        if a_ts is None or len(a_ts) == 0:
            continue
        t = starts[i]
        lo = np.searchsorted(a_ts, t - horizon, side="left")
        hi = np.searchsorted(a_ts, t, side="left")
        if hi > lo:
            detected[i] = True
            earliest = a_ts[lo]
            lead_time_hours[i] = (t - earliest) / np.timedelta64(1, "h")
    return detected, lead_time_hours


def alert_summary(alerts, raw_candidates_above_threshold, episodes_in_period, horizon_hours, n_days):
    detected, lead_time_hours = episode_level_recall(alerts, episodes_in_period, horizon_hours)
    valid_lead = lead_time_hours[~np.isnan(lead_time_hours)]
    n_raw = len(raw_candidates_above_threshold)
    n_kept = len(alerts)
    return {
        "n_alerts": n_kept,
        "alerts_per_day": n_kept / max(n_days, 1),
        "unique_assets_alerted_per_day": (
            alerts.assign(_day=pd.to_datetime(alerts["ts"]).dt.floor("D")).groupby("_day")["channel_id"].nunique().mean()
            if n_kept else 0.0
        ),
        "duplicate_alert_rate": (1 - n_kept / n_raw) if n_raw else 0.0,
        "alert_precision": float(alerts["target"].mean()) if n_kept else None,
        "failure_episodes_total": int(len(episodes_in_period)),
        "failure_episodes_detected": int(detected.sum()),
        "failure_episodes_missed": int((~detected).sum()),
        "end_to_end_recall": float(detected.mean()) if len(episodes_in_period) else None,
        "median_lead_time_hours": float(np.median(valid_lead)) if len(valid_lead) else None,
        "p25_lead_time_hours": float(np.percentile(valid_lead, 25)) if len(valid_lead) else None,
        "p75_lead_time_hours": float(np.percentile(valid_lead, 75)) if len(valid_lead) else None,
    }
