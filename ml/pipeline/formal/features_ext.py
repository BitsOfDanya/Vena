import numpy as np
import pandas as pd
from numba import njit

from pipeline import config

INTENSITY_TAUS = (3600.0, 21600.0, 86400.0, 604800.0, 2592000.0)
INTENSITY_TAU_NAMES = ("1h", "6h", "24h", "7d", "30d")
INTENSITY_KINDS = ("all", "alarm", "fail", "trans")
HOURLY_WINDOWS = (1, 3, 24)
EPOCH = np.datetime64("2019-01-01T00:00:00")
DT_BUCKET_EDGES = (1.0, 60.0, 3600.0)


def to_seconds(ts):
    return np.asarray(ts).astype("datetime64[s]").astype("int64").astype(np.float64)


def _prepare(cand, events):
    ev = events[["channel_id", "ts", "alarm_flag", "raw_value"]].copy()
    ev["channel_id"] = ev["channel_id"].astype(str)
    ev = ev.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    cd = pd.DataFrame({"channel_id": cand["channel_id"].astype(str).values, "ts": cand["ts"].values,
                       "pos": np.arange(len(cand))})
    cd = cd.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    return ev, cd


def _segments(keys):
    if len(keys) == 0:
        return {}
    change = np.flatnonzero(keys[1:] != keys[:-1]) + 1
    starts = np.concatenate([[0], change])
    ends = np.concatenate([change, [len(keys)]])
    return {keys[s]: (s, e) for s, e in zip(starts, ends)}


@njit(cache=True)
def _intensity_kernel(ev_t, ev_w, c_t, taus):
    n_c = len(c_t)
    nt = len(taus)
    nw = ev_w.shape[1]
    out = np.zeros((n_c, nw * nt))
    s = np.zeros((nw, nt))
    last = ev_t[0] if len(ev_t) > 0 else 0.0
    j = 0
    for i in range(n_c):
        t = c_t[i]
        while j < len(ev_t) and ev_t[j] <= t:
            dt = ev_t[j] - last
            for a in range(nt):
                dec = np.exp(-dt / taus[a])
                for b in range(nw):
                    s[b, a] = s[b, a] * dec + ev_w[j, b]
            last = ev_t[j]
            j += 1
        dt = t - last
        for a in range(nt):
            dec = np.exp(-dt / taus[a])
            for b in range(nw):
                out[i, b * nt + a] = s[b, a] * dec
    return out


def intensity_features(cand, events):
    ev, cd = _prepare(cand, events)
    state = pd.factorize(ev["raw_value"].astype(str))[0]
    same = np.concatenate([[False], (ev["channel_id"].values[1:] == ev["channel_id"].values[:-1])])
    prev_state = np.concatenate([[-1], state[:-1]])
    trans = (same & (state != prev_state)).astype(np.float64)
    w = np.column_stack([
        np.ones(len(ev)),
        ev["alarm_flag"].values.astype(np.float64),
        (ev["raw_value"].astype(str) == config.FAULT_LITERAL).values.astype(np.float64),
        trans,
    ])
    ev_t = to_seconds(ev["ts"].values)
    c_t = to_seconds(cd["ts"].values)
    taus = np.array(INTENSITY_TAUS)
    ev_seg = _segments(ev["channel_id"].values)
    cd_seg = _segments(cd["channel_id"].values)
    nt = len(taus)
    out = np.zeros((len(cd), len(INTENSITY_KINDS) * nt))
    for cid, (cs, ce) in cd_seg.items():
        if cid not in ev_seg:
            continue
        es, ee = ev_seg[cid]
        out[cs:ce] = _intensity_kernel(ev_t[es:ee], w[es:ee], c_t[cs:ce], taus)
    names = [f"int_{k}_{n}" for k in INTENSITY_KINDS for n in INTENSITY_TAU_NAMES]
    frame = pd.DataFrame(out, columns=names)
    rate = {n: frame[[f"int_{k}_{n}" for k in INTENSITY_KINDS]].values / tau
            for n, tau in zip(INTENSITY_TAU_NAMES, INTENSITY_TAUS)}
    for ki, kind in enumerate(INTENSITY_KINDS[:3]):
        for short, long_ in (("1h", "24h"), ("6h", "7d"), ("24h", "30d")):
            frame[f"int_ratio_{kind}_{short}_{long_}"] = rate[short][:, ki] / (rate[long_][:, ki] + 1e-9)
    frame.index = cd["pos"].values
    return frame.sort_index().reset_index(drop=True)


def hourly_baseline_features(cand, events, lookback_days=28):
    ev, cd = _prepare(cand, events)
    channels = np.unique(np.concatenate([ev["channel_id"].unique(), cd["channel_id"].unique()]))
    ch_index = {c: i for i, c in enumerate(channels)}
    t0 = to_seconds(np.array([EPOCH]))[0]
    ev_t = to_seconds(ev["ts"].values)
    c_t = to_seconds(cd["ts"].values)
    n_days = int(np.ceil((max(ev_t.max(), c_t.max()) - t0) / 86400.0)) + 2
    n_bins = n_days * 24
    ev_ch = np.array([ch_index[c] for c in ev["channel_id"].values])
    ev_bin = ((ev_t - t0) // 3600).astype(np.int64)
    counts = np.bincount(ev_ch * n_bins + ev_bin, minlength=len(channels) * n_bins).reshape(len(channels), n_days, 24)
    cs = np.cumsum(counts, axis=1, dtype=np.float64)
    padded = np.concatenate([np.zeros((len(channels), lookback_days + 1, 24)), cs], axis=1)
    idx = np.arange(n_days) + lookback_days + 1
    lag_sum = padded[:, idx - 1, :] - padded[:, idx - 1 - lookback_days, :]
    avail = np.minimum(np.arange(n_days), lookback_days).astype(np.float64)
    expected = np.where(avail[None, :, None] > 0, lag_sum / np.maximum(avail[None, :, None], 1.0), 0.0)
    exp_flat = expected.reshape(len(channels), n_bins)
    cnt_flat = counts.reshape(len(channels), n_bins).astype(np.float64)
    ccnt = np.concatenate([np.zeros((len(channels), 1)), np.cumsum(cnt_flat, axis=1)], axis=1)
    cexp = np.concatenate([np.zeros((len(channels), 1)), np.cumsum(exp_flat, axis=1)], axis=1)
    c_ch = np.array([ch_index[c] for c in cd["channel_id"].values])
    c_bin = ((c_t - t0) // 3600).astype(np.int64)
    out = {}
    for w in HOURLY_WINDOWS:
        lo = np.maximum(c_bin - w, 0)
        cur = ccnt[c_ch, c_bin] - ccnt[c_ch, lo]
        exp = cexp[c_ch, c_bin] - cexp[c_ch, lo]
        out[f"hb_cur_{w}h"] = cur
        out[f"hb_exp_{w}h"] = exp
        out[f"hb_dev_{w}h"] = cur - exp
        out[f"hb_z_{w}h"] = (cur - exp) / np.sqrt(exp + 1.0)
    out["hb_silence_3h"] = np.where(out["hb_cur_3h"] == 0, out["hb_exp_3h"], 0.0)
    out["hb_burst_3h"] = np.maximum(out["hb_dev_3h"], 0.0)
    out["hb_history"] = avail[np.minimum(c_bin // 24, n_days - 1)] / lookback_days
    frame = pd.DataFrame(out)
    frame.index = cd["pos"].values
    return frame.sort_index().reset_index(drop=True)


def _dt_bucket(dt):
    b = np.zeros(len(dt), dtype=np.int64)
    for e in DT_BUCKET_EDGES:
        b += (dt > e).astype(np.int64)
    return b


@njit(cache=True)
def _window_stats(ev_t, ev_v1, ev_v2, ev_rare, c_t, win):
    n_c = len(c_t)
    out = np.zeros((n_c, 6))
    j = 0
    lo = 0
    for i in range(n_c):
        t = c_t[i]
        while j < len(ev_t) and ev_t[j] <= t:
            j += 1
        while lo < j and ev_t[lo] <= t - win:
            lo += 1
        m1 = 0.0
        m2 = 0.0
        s1 = 0.0
        s2 = 0.0
        r = 0.0
        for k in range(lo, j):
            if ev_v1[k] > m1:
                m1 = ev_v1[k]
            if ev_v2[k] > m2:
                m2 = ev_v2[k]
            s1 += ev_v1[k]
            s2 += ev_v2[k]
            r += ev_rare[k]
        n = j - lo
        out[i, 0] = m1
        out[i, 1] = m2
        out[i, 2] = s1 / n if n > 0 else 0.0
        out[i, 3] = s2 / n if n > 0 else 0.0
        out[i, 4] = r
        out[i, 5] = n
    return out


def markov_features(cand, events, train_end_ts, alpha=0.5, backoff_k=20.0):
    ev, cd = _prepare(cand, events)
    cats = pd.Categorical(ev["raw_value"].astype(str))
    state = cats.codes.astype(np.int64)
    n_s = len(cats.categories)
    ch = ev["channel_id"].values
    same1 = np.concatenate([[False], ch[1:] == ch[:-1]])
    same2 = np.concatenate([[False, False], (ch[2:] == ch[:-2]) & same1[2:] & same1[1:-1]])
    p1 = np.where(same1, np.concatenate([[n_s], state[:-1]]), n_s)
    p2 = np.where(same2, np.concatenate([[n_s, n_s], state[:-2]]), n_s)
    ev_t = to_seconds(ev["ts"].values)
    dt = np.where(same1, ev_t - np.concatenate([[ev_t[0]], ev_t[:-1]]), 1e9)
    bucket = _dt_bucket(dt)
    train = to_seconds(np.array([train_end_ts]))[0]
    tr = ev_t <= train
    c2 = np.zeros((n_s + 1, n_s))
    np.add.at(c2, (p1[tr], state[tr]), 1.0)
    c3 = np.zeros((n_s + 1, n_s + 1, n_s))
    np.add.at(c3, (p2[tr], p1[tr], state[tr]), 1.0)
    ct = np.zeros((len(DT_BUCKET_EDGES) + 1, n_s + 1, n_s))
    np.add.at(ct, (bucket[tr], p1[tr], state[tr]), 1.0)
    prob2 = (c2 + alpha) / (c2.sum(axis=1, keepdims=True) + alpha * n_s)
    n3 = c3.sum(axis=2, keepdims=True)
    lam3 = n3 / (n3 + backoff_k)
    prob3 = lam3 * (c3 / np.maximum(n3, 1.0)) + (1 - lam3) * prob2[None, :, :]
    nt_ = ct.sum(axis=2, keepdims=True)
    lamt = nt_ / (nt_ + backoff_k)
    probt = lamt * (ct / np.maximum(nt_, 1.0)) + (1 - lamt) * prob2[None, :, :]
    s_bi = -np.log(prob2[p1, state])
    s_tri = -np.log(prob3[p2, p1, state])
    s_time = -np.log(probt[bucket, p1, state])
    rare_thr = np.quantile(s_tri[tr], 0.99) if tr.any() else np.inf
    rare = (s_tri > rare_thr).astype(np.float64)
    c_t = to_seconds(cd["ts"].values)
    ev_seg = _segments(ch)
    cd_seg = _segments(cd["channel_id"].values)
    n_c = len(cd)
    last = np.zeros((n_c, 3))
    w6 = np.zeros((n_c, 6))
    w24 = np.zeros((n_c, 6))
    for cid, (cs, ce) in cd_seg.items():
        if cid not in ev_seg:
            continue
        es, ee = ev_seg[cid]
        et = ev_t[es:ee]
        idx = np.searchsorted(et, c_t[cs:ce], side="right") - 1
        has = idx >= 0
        for col, arr in enumerate((s_bi, s_tri, s_time)):
            v = np.zeros(ce - cs)
            v[has] = arr[es:ee][idx[has]]
            last[cs:ce, col] = v
        w6[cs:ce] = _window_stats(et, s_bi[es:ee], s_tri[es:ee], rare[es:ee], c_t[cs:ce], 21600.0)
        w24[cs:ce] = _window_stats(et, s_bi[es:ee], s_tri[es:ee], rare[es:ee], c_t[cs:ce], 86400.0)
    frame = pd.DataFrame({
        "mk_bi_last": last[:, 0], "mk_tri_last": last[:, 1], "mk_time_last": last[:, 2],
        "mk_bi_max_6h": w6[:, 0], "mk_tri_max_6h": w6[:, 1], "mk_bi_mean_6h": w6[:, 2], "mk_tri_mean_6h": w6[:, 3],
        "mk_rare_6h": w6[:, 4], "mk_bi_max_24h": w24[:, 0], "mk_tri_max_24h": w24[:, 1],
        "mk_bi_mean_24h": w24[:, 2], "mk_tri_mean_24h": w24[:, 3], "mk_rare_24h": w24[:, 4],
    })
    frame.index = cd["pos"].values
    return frame.sort_index().reset_index(drop=True)


def channel_history_rate(cand, label, lag_hours, prior_strength=20.0, fallback_rate=0.2):
    ts = to_seconds(cand["ts"].values)
    ch = cand["channel_id"].astype(str).values
    y = np.asarray(label, dtype=np.float64)
    order = np.lexsort((ts, ch))
    ch_s, ts_s, y_s = ch[order], ts[order], y[order]
    all_order = np.argsort(ts, kind="stable")
    ts_all = ts[all_order]
    cum_all = np.concatenate([[0.0], np.cumsum(y[all_order])])
    lag = lag_hours * 3600.0
    idx_all = np.searchsorted(ts_all, ts - lag, side="right")
    g_rate = np.where(idx_all > 0, cum_all[idx_all] / np.maximum(idx_all, 1), fallback_rate)
    rate = np.zeros(len(cand))
    n_past = np.zeros(len(cand))
    for cid, (s, e) in _segments(ch_s).items():
        t_seg = ts_s[s:e]
        cum = np.concatenate([[0.0], np.cumsum(y_s[s:e])])
        idx = np.searchsorted(t_seg, t_seg - lag, side="right")
        pos = order[s:e]
        n_past[pos] = idx
        rate[pos] = (cum[idx] + prior_strength * g_rate[pos]) / (idx + prior_strength)
    return pd.DataFrame({"chan_hist_rate": rate, "chan_hist_n": n_past})
