import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, precision_recall_curve

from pipeline import alerts as alerts_mod

TOPK_FRACTIONS = [0.001, 0.005, 0.01, 0.02, 0.05]


def evaluate(y_true, y_score):
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    result = {"n": len(y_true), "n_positive": int(y_true.sum())}

    keys = ["roc_auc", "avg_precision", "precision_at_recall_0.5", "recall_at_precision_0.7"]
    keys += [f"precision_top_{k*100:g}pct" for k in TOPK_FRACTIONS]
    keys += [f"recall_top_{k*100:g}pct" for k in TOPK_FRACTIONS]

    if y_true.sum() == 0 or y_true.sum() == len(y_true):
        result.update({k: None for k in keys})
        return result

    result["roc_auc"] = round(roc_auc_score(y_true, y_score), 4)
    result["avg_precision"] = round(average_precision_score(y_true, y_score), 4)

    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    idx = np.where(recall[:-1] >= 0.5)[0]
    result["precision_at_recall_0.5"] = round(float(precision[idx[-1]]), 4) if len(idx) else None

    idx2 = np.where(precision[:-1] >= 0.7)[0]
    result["recall_at_precision_0.7"] = round(float(recall[idx2[0]]), 4) if len(idx2) else None

    for k in TOPK_FRACTIONS:
        n_top = max(int(len(y_score) * k), 1)
        top_idx = np.argsort(-y_score)[:n_top]
        p_k = y_true[top_idx].mean()
        r_k = y_true[top_idx].sum() / y_true.sum()
        result[f"precision_top_{k*100:g}pct"] = round(float(p_k), 4)
        result[f"recall_top_{k*100:g}pct"] = round(float(r_k), 4)

    return result


def evaluate_daily_topk(ts, y_true, y_score, k_fracs=TOPK_FRACTIONS):
    df = pd.DataFrame({
        "day": pd.to_datetime(np.asarray(ts)).floor("D"),
        "y": np.asarray(y_true),
        "score": np.asarray(y_score),
    })
    total_positive = df["y"].sum()
    result = {"n_days": int(df["day"].nunique())}
    for k in k_fracs:
        tp = 0
        selected = 0
        for _, g in df.groupby("day"):
            n_top = max(int(len(g) * k), 1)
            top = g.nlargest(n_top, "score")
            tp += top["y"].sum()
            selected += len(top)
        precision = tp / selected if selected else None
        recall = tp / total_positive if total_positive else None
        result[f"daily_precision_top_{k*100:g}pct"] = round(float(precision), 4) if precision is not None else None
        result[f"daily_recall_top_{k*100:g}pct"] = round(float(recall), 4) if recall is not None else None
    return result


def evaluate_daily_topk_fixed(ts, y_true, y_score, counts=(5, 10, 20, 50)):
    df = pd.DataFrame({
        "day": pd.to_datetime(np.asarray(ts)).floor("D"),
        "y": np.asarray(y_true),
        "score": np.asarray(y_score),
    })
    total_positive = df["y"].sum()
    result = {}
    for k in counts:
        tp = 0
        selected = 0
        for _, g in df.groupby("day"):
            top = g.nlargest(min(k, len(g)), "score")
            tp += top["y"].sum()
            selected += len(top)
        precision = tp / selected if selected else None
        recall = tp / total_positive if total_positive else None
        result[f"precision_top{k}_per_day"] = round(float(precision), 4) if precision is not None else None
        result[f"recall_top{k}_per_day"] = round(float(recall), 4) if recall is not None else None
    return result


def evaluate_predictions(channel_id, prediction_time, y_true, risk_score, episodes=None,
                          horizon_hours=None, cooldown_hours=24, topk_frac=0.01):
    y_true = np.asarray(y_true)
    risk_score = np.asarray(risk_score)
    result = evaluate(y_true, risk_score)
    result.update(evaluate_daily_topk(prediction_time, y_true, risk_score))

    if episodes is not None and horizon_hours is not None:
        df = pd.DataFrame({
            "channel_id": np.asarray(channel_id),
            "ts": pd.to_datetime(np.asarray(prediction_time)),
            "target": y_true,
            "_score": risk_score,
        })
        raw_topk = alerts_mod.raw_daily_topk(df, "_score", topk_frac, mode="frac")
        alerted = alerts_mod._apply_cooldown(raw_topk, cooldown_hours)
        n_days = max((df["ts"].max() - df["ts"].min()).total_seconds() / 86400.0, 1.0)
        result.update(alerts_mod.alert_summary(alerted, raw_topk, episodes, horizon_hours, n_days))

    return result


def morning_lists(scored, episodes, horizon_hours, counts=(5, 10), cooldown_days=1):
    scored = scored[["channel_id", "ts", "score"]].assign(channel_id=scored["channel_id"].astype(str)).sort_values("ts")
    starts = episodes[["channel_id", "episode_start"]].assign(channel_id=episodes["channel_id"].astype(str))
    starts_by_channel = {key: np.sort(group.to_numpy(dtype="datetime64[ns]"))
                         for key, group in starts.groupby("channel_id")["episode_start"]}
    horizon = np.timedelta64(int(horizon_hours), "h")
    first, last = scored["ts"].min().normalize() + pd.Timedelta(days=1), scored["ts"].max().normalize()
    days = pd.date_range(first, last - pd.Timedelta(hours=horizon_hours), freq="D")
    lists = []
    for day in days:
        window = scored.loc[(scored["ts"] >= day - pd.Timedelta(days=1)) & (scored["ts"] < day)]
        latest = window.groupby("channel_id").tail(1).sort_values("score", ascending=False)
        lists.append((day, latest["channel_id"].tolist()))
    period_start, period_end = days[0], days[-1] + pd.Timedelta(days=1)
    in_period = starts.loc[(starts["episode_start"] >= period_start) & (starts["episode_start"] < period_end)]
    result = {}
    for count in counts:
        for cooldown in (0, cooldown_days):
            recent, hits, selected, warned = {}, 0, 0, set()
            for day, ranked in lists:
                moment = np.datetime64(day, "ns")
                chosen = [c for c in ranked
                          if cooldown == 0 or c not in recent or (day - recent[c]).days > cooldown][:count]
                for channel in chosen:
                    recent[channel] = day
                    times = starts_by_channel.get(channel)
                    selected += 1
                    if times is None:
                        continue
                    low = np.searchsorted(times, moment, side="left")
                    high = np.searchsorted(times, moment + horizon, side="right")
                    if high > low:
                        hits += 1
                        warned.update((channel, t) for t in times[low:high])
            key = f"top{count}" + ("_no_repeat" if cooldown else "")
            result[key] = {
                "precision": round(hits / selected, 4) if selected else None,
                "episodes_warned": len(warned),
                "episode_share": round(len(warned) / max(len(in_period), 1), 4),
                "distinct_channels": len(recent),
            }
    return result
