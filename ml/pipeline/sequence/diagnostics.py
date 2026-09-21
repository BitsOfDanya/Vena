import numpy as np


def time_span_stats(event_index, channel_ids, ts_sec, max_len, sample_size=20000, seed=0):
    channel_ids = np.asarray(channel_ids)
    ts_sec = np.asarray(ts_sec)
    n = len(ts_sec)
    if n > sample_size:
        rng = np.random.default_rng(seed)
        sel = rng.choice(n, size=sample_size, replace=False)
    else:
        sel = np.arange(n)

    spans_days = []
    event_counts = []
    for i in sel:
        window_ts, window_state, window_alarm, prev_ts = event_index.window(channel_ids[i], ts_sec[i], max_len)
        event_counts.append(len(window_ts))
        if len(window_ts) >= 2:
            spans_days.append((window_ts[-1] - window_ts[0]) / 86400.0)

    spans_days = np.array(spans_days)
    event_counts = np.array(event_counts)
    return {
        "n_sampled": int(len(sel)),
        "median_span_days": float(np.median(spans_days)) if len(spans_days) else None,
        "p25_span_days": float(np.percentile(spans_days, 25)) if len(spans_days) else None,
        "p75_span_days": float(np.percentile(spans_days, 75)) if len(spans_days) else None,
        "median_events_in_window": float(np.median(event_counts)) if len(event_counts) else None,
        "frac_windows_at_max_len": float((event_counts == max_len).mean()) if len(event_counts) else None,
    }
