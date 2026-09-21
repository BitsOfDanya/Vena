import numpy as np
import pandas as pd

from pipeline import config

NON_STATE_VALUES = {"Норма", "Неопределен", "Не определено"}


def is_numeric_value(series):
    return pd.to_numeric(series.astype(str), errors="coerce").notna()


def state_episodes(events, state, gap_hours=config.EPISODE_GAP_HOURS):
    sel = events.loc[events["raw_value"] == state, ["channel_id", "ts"]].sort_values(["channel_id", "ts"])
    if sel.empty:
        return pd.DataFrame(columns=["channel_id", "episode_start", "episode_end", "n_ticks"])
    gap = sel.groupby("channel_id", observed=True)["ts"].diff().dt.total_seconds() / 3600
    new = gap.isna() | (gap > gap_hours)
    sel = sel.assign(episode_id=new.groupby(sel["channel_id"], observed=True).cumsum())
    grouped = sel.groupby(["channel_id", "episode_id"], observed=True)["ts"].agg(["min", "max", "size"]).reset_index()
    grouped.columns = ["channel_id", "episode_id", "episode_start", "episode_end", "n_ticks"]
    return grouped.drop(columns="episode_id").sort_values(["channel_id", "episode_start"]).reset_index(drop=True)


def episode_summary(episodes):
    if episodes.empty:
        return {"n_episodes": 0}
    eps = episodes.sort_values(["channel_id", "episode_start"])
    dur = (eps["episode_end"] - eps["episode_start"]).dt.total_seconds() / 60.0
    gap = eps.groupby("channel_id", observed=True)["episode_start"].diff().dt.total_seconds() / 3600.0
    per_channel = eps.groupby("channel_id", observed=True).size().sort_values(ascending=False)
    top10 = max(int(np.ceil(0.1 * len(per_channel))), 1)
    years = eps["episode_start"].dt.year.value_counts().sort_index()
    return {
        "n_episodes": int(len(eps)),
        "n_channels_with_episodes": int(len(per_channel)),
        "episodes_per_channel_median": float(per_channel.median()),
        "top10pct_channels_share": float(per_channel.iloc[:top10].sum() / len(eps)),
        "first_year": int(years.index.min()),
        "last_year": int(years.index.max()),
        "yearly_counts": ";".join(f"{int(y)}:{int(n)}" for y, n in years.items()),
        "median_duration_min": float(dur.median()),
        "p25_duration_min": float(dur.quantile(0.25)),
        "p75_duration_min": float(dur.quantile(0.75)),
        "single_tick_fraction": float((eps["n_ticks"] == 1).mean()),
        "recurring_le_24h": float((gap <= 24).sum() / len(eps)),
        "recurring_le_7d": float((gap <= 168).sum() / len(eps)),
        "median_inter_episode_h": float(gap.median()) if gap.notna().any() else None,
    }


def horizon_base_rate(events, episodes, horizon_hours, sample=200000, seed=0):
    if episodes.empty or events.empty:
        return 0.0
    ev = events[["channel_id", "ts"]]
    if len(ev) > sample:
        ev = ev.sample(sample, random_state=seed)
    starts = {cid: np.sort(g["episode_start"].values) for cid, g in episodes.groupby("channel_id", observed=True)}
    ts = ev["ts"].values
    hit = np.zeros(len(ev), dtype=bool)
    horizon = np.timedelta64(int(horizon_hours * 3600), "s")
    for cid, pos in ev.reset_index(drop=True).groupby("channel_id", observed=True).indices.items():
        s = starts.get(cid)
        if s is None:
            continue
        t = ts[pos]
        lo = np.searchsorted(s, t, side="right")
        hi = np.searchsorted(s, t + horizon, side="right")
        hit[pos] = hi > lo
    return float(hit.mean())


def transition_counts(events, min_count=1):
    ev = events[["channel_id", "ts", "raw_value"]].sort_values(["channel_id", "ts"], kind="stable")
    prev = ev.groupby("channel_id", observed=True)["raw_value"].shift(1)
    dt = ev.groupby("channel_id", observed=True)["ts"].diff().dt.total_seconds()
    tr = pd.DataFrame({"prev_state": prev.astype(str), "state": ev["raw_value"].astype(str), "dt": dt,
                       "channel_id": ev["channel_id"]})
    tr = tr[prev.notna() & (tr["prev_state"] != tr["state"])]
    out = tr.groupby(["prev_state", "state"]).agg(
        n=("dt", "size"), n_channels=("channel_id", "nunique"), median_dt_s=("dt", "median")).reset_index()
    return out[out["n"] >= min_count].sort_values("n", ascending=False).reset_index(drop=True)


def literal_only(events):
    return events.loc[~is_numeric_value(events["raw_value"])]


def sustained_onsets(events, state, min_minutes):
    ev = events[["channel_id", "ts", "raw_value"]].sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    prev = ev.groupby("channel_id", observed=True)["raw_value"].shift(1)
    new_run = ev["raw_value"] != prev
    runs = ev.loc[new_run, ["channel_id", "ts", "raw_value"]].reset_index(drop=True)
    runs["run_end"] = runs.groupby("channel_id", observed=True)["ts"].shift(-1)
    dwell = (runs["run_end"] - runs["ts"]).dt.total_seconds() / 60.0
    keep = (runs["raw_value"] == state) & (dwell >= min_minutes)
    out = runs.loc[keep, ["channel_id", "ts", "run_end"]].rename(columns={"ts": "episode_start", "run_end": "episode_end"})
    out["n_ticks"] = 1
    return out.reset_index(drop=True)
