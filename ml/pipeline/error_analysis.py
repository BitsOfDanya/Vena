import numpy as np
import pandas as pd

from pipeline import alerts as alerts_mod


def fn_breakdown(candidates_df, episodes_in_period, horizon_hours, alerts_df):
    covered = alerts_mod.candidate_coverage(candidates_df[["channel_id", "ts"]], episodes_in_period, horizon_hours)
    detected, _ = alerts_mod.episode_level_recall(alerts_df, episodes_in_period, horizon_hours)
    n = len(episodes_in_period)
    candidate_miss = int((~covered).sum())
    model_miss = int((covered & ~detected).sum())
    detected_count = int(detected.sum())
    return {
        "total_episodes": n,
        "detected": detected_count,
        "candidate_generator_miss": candidate_miss,
        "model_miss": model_miss,
        "candidate_generator_miss_share": candidate_miss / n if n else None,
        "model_miss_share": model_miss / n if n else None,
    }


def near_miss_rate(fp_df, episodes, window_hours):
    if fp_df.empty:
        return None
    window = np.timedelta64(int(window_hours), "h")
    ep_by_channel = {
        cid: np.sort(g["episode_start"].values) for cid, g in episodes.groupby("channel_id", observed=True)
    } if len(episodes) else {}
    channels = fp_df["channel_id"].values
    ts_vals = fp_df["ts"].values
    hits = 0
    for i in range(len(fp_df)):
        starts = ep_by_channel.get(channels[i])
        if starts is None or len(starts) == 0:
            continue
        t = ts_vals[i]
        lo = np.searchsorted(starts, t, side="right")
        hi = np.searchsorted(starts, t + window, side="right")
        if hi > lo:
            hits += 1
    return hits / len(fp_df)


def fp_near_miss_summary(df, score_col, threshold, episodes, horizon_hours, windows_hours=(48, 72, 168)):
    pred_mask = df[score_col] >= threshold
    fp_df = df[pred_mask & (df["target"] == 0)]
    result = {"n_fp": len(fp_df)}
    for w in windows_hours:
        result[f"near_miss_{w}h"] = near_miss_rate(fp_df, episodes, w)
    return result


def group_error_stats(df, score_col, threshold, feature_cols):
    pred = (df[score_col] >= threshold).astype(int)
    y = df["target"].values
    groups = {
        "true_positive": (pred == 1) & (y == 1),
        "false_positive": (pred == 1) & (y == 0),
        "false_negative": (pred == 0) & (y == 1),
        "true_negative": (pred == 0) & (y == 0),
    }
    rows = []
    for label, mask in groups.items():
        sub = df.loc[mask]
        row = {"group": label, "n": int(mask.sum())}
        for col in feature_cols:
            row[f"mean_{col}"] = float(sub[col].mean()) if len(sub) else None
        rows.append(row)
    return pd.DataFrame(rows)
