import numpy as np
import pandas as pd

from pipeline import config

WINDOWS_SECONDS = {
    "10m": 600,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
    "7d": 604800,
    "30d": 2592000,
}

FAIL_WINDOWS_SECONDS = {
    "1d": 86400, "3d": 259200, "7d": 604800, "14d": 1209600, "30d": 2592000, "90d": 7776000,
}

ON_LITERAL = "Включен"
OFF_LITERAL = "Выключен"
DUTY_CYCLE_WINDOWS_SECONDS = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}


def _rolling_entropy(codes, window_events):
    n = len(codes)
    out = np.zeros(n)
    if n == 0:
        return out
    max_code = codes.max() + 1 if n else 1
    for i in range(n):
        lo = max(0, i - window_events)
        segment = codes[lo:i + 1]
        if len(segment) == 0:
            continue
        counts = np.bincount(segment, minlength=max_code)
        counts = counts[counts > 0]
        p = counts / counts.sum()
        out[i] = -(p * np.log2(p)).sum()
    return out


def compute_global_rates(events, train_end_year):
    train_events = events[events["ts"].dt.year <= train_end_year]
    if train_events.empty:
        return {"event": 0.0, "alarm": 0.0, "failure": 0.0}
    n_days = max((train_events["ts"].max() - train_events["ts"].min()).total_seconds() / 86400.0, 1.0)
    n_channels = max(train_events["channel_id"].nunique(), 1)
    denom = n_days * n_channels
    event_rate = len(train_events) / denom
    alarm_rate = float(train_events["alarm_flag"].sum()) / denom
    failure_rate = float((train_events["raw_value"] == config.FAULT_LITERAL).sum()) / denom
    return {"event": event_rate, "alarm": alarm_rate, "failure": failure_rate}


def _ewma_daily_lookup(cand_ts_sec, ev_ts_sec, weights, halflife_days):
    n = len(cand_ts_sec)
    if len(ev_ts_sec) == 0:
        return np.zeros(n)
    ev_day = ev_ts_sec // 86400
    day_min = ev_day.min()
    n_days = int(ev_day.max() - day_min) + 1
    daily = np.zeros(n_days)
    np.add.at(daily, ev_day - day_min, weights)
    ewma = pd.Series(daily).ewm(halflife=halflife_days, adjust=False).mean().values
    cand_day = (cand_ts_sec // 86400) - day_min - 1
    valid = cand_day >= 0
    safe_day = np.clip(cand_day, 0, n_days - 1)
    return np.where(valid, ewma[safe_day], 0.0)


def _segment_table(ev_ts_sec, ev_value):
    state_code = np.where(ev_value == ON_LITERAL, 1, np.where(ev_value == OFF_LITERAL, 0, -1))
    changes = np.concatenate([[True], state_code[1:] != state_code[:-1]])
    seg_start_idx = np.where(changes)[0]
    return state_code[seg_start_idx], ev_ts_sec[seg_start_idx]


def _duty_cycle_features(cand_ts_sec, ev_ts_sec, ev_value):
    n = len(cand_ts_sec)
    out = {}
    keys_zero = ["time_in_current_state_hours", "mean_on_duration_hours", "mean_off_duration_hours",
                 "max_on_duration_hours", "max_off_duration_hours"]
    if len(ev_ts_sec) == 0:
        for k in keys_zero:
            out[k] = np.zeros(n)
        for wname in DUTY_CYCLE_WINDOWS_SECONDS:
            out[f"transition_count_{wname}"] = np.zeros(n)
            out[f"on_off_cycles_{wname}"] = np.zeros(n)
        return out

    seg_state, seg_start_ts = _segment_table(ev_ts_sec, ev_value)
    n_seg = len(seg_start_ts)

    idx_seg_le = np.searchsorted(seg_start_ts, cand_ts_sec, side="right")
    last_seg_idx = np.clip(idx_seg_le - 1, 0, n_seg - 1)
    has_seg = idx_seg_le > 0
    out["time_in_current_state_hours"] = np.where(has_seg, (cand_ts_sec - seg_start_ts[last_seg_idx]) / 3600.0, 0.0)

    if n_seg > 1:
        completed_end_ts = seg_start_ts[1:]
        completed_state = seg_state[:-1]
        completed_duration = (seg_start_ts[1:] - seg_start_ts[:-1]) / 3600.0
    else:
        completed_end_ts = np.array([], dtype=np.int64)
        completed_state = np.array([], dtype=np.int64)
        completed_duration = np.array([], dtype=float)

    on_mask = completed_state == 1
    off_mask = completed_state == 0
    on_end_ts = completed_end_ts[on_mask]
    on_durations = completed_duration[on_mask]
    off_end_ts = completed_end_ts[off_mask]
    off_durations = completed_duration[off_mask]

    on_cumsum = np.concatenate([[0.0], np.cumsum(on_durations)])
    off_cumsum = np.concatenate([[0.0], np.cumsum(off_durations)])
    on_cummax = np.concatenate([[0.0], np.maximum.accumulate(on_durations)]) if len(on_durations) else np.zeros(1)
    off_cummax = np.concatenate([[0.0], np.maximum.accumulate(off_durations)]) if len(off_durations) else np.zeros(1)

    idx_on = np.searchsorted(on_end_ts, cand_ts_sec, side="right")
    idx_off = np.searchsorted(off_end_ts, cand_ts_sec, side="right")

    out["mean_on_duration_hours"] = np.where(idx_on > 0, on_cumsum[idx_on] / np.maximum(idx_on, 1), 0.0)
    out["mean_off_duration_hours"] = np.where(idx_off > 0, off_cumsum[idx_off] / np.maximum(idx_off, 1), 0.0)
    out["max_on_duration_hours"] = on_cummax[idx_on]
    out["max_off_duration_hours"] = off_cummax[idx_off]

    transition_ts = seg_start_ts[1:] if n_seg > 1 else np.array([], dtype=np.int64)
    cycle_ts = on_end_ts

    for wname, wsec in DUTY_CYCLE_WINDOWS_SECONDS.items():
        idx_t_hi = np.searchsorted(transition_ts, cand_ts_sec, side="right")
        idx_t_lo = np.searchsorted(transition_ts, cand_ts_sec - wsec, side="right")
        out[f"transition_count_{wname}"] = (idx_t_hi - idx_t_lo).astype(float)

        idx_c_hi = np.searchsorted(cycle_ts, cand_ts_sec, side="right")
        idx_c_lo = np.searchsorted(cycle_ts, cand_ts_sec - wsec, side="right")
        out[f"on_off_cycles_{wname}"] = (idx_c_hi - idx_c_lo).astype(float)

    return out


def _channel_features(cand_ts, ev_ts, ev_alarm, ev_value, fail_starts, numeric_mode=False,
                       duty_cycle_mode=False, global_rates=None):
    n_cand = len(cand_ts)
    ev_ts_sec = ev_ts.astype("datetime64[s]").astype(np.int64)
    cand_ts_sec = cand_ts.astype("datetime64[s]").astype(np.int64)
    global_rates = global_rates or {"event": 0.0, "alarm": 0.0, "failure": 0.0}
    alpha = config.PRIOR_SMOOTHING_ALPHA

    idx_le = np.searchsorted(ev_ts_sec, cand_ts_sec, side="right")

    alarm_cumsum = np.concatenate([[0], np.cumsum(ev_alarm)])

    out = {}
    for wname, wsec in WINDOWS_SECONDS.items():
        idx_from = np.searchsorted(ev_ts_sec, cand_ts_sec - wsec, side="right")
        out[f"events_{wname}"] = (idx_le - idx_from).astype(float)
        if wname in ("1h", "24h", "7d", "30d"):
            out[f"alarms_{wname}"] = alarm_cumsum[idx_le] - alarm_cumsum[idx_from]

    rate_1h = out["events_1h"]
    rate_24h = out["events_24h"] / 24.0
    out["event_rate_delta"] = rate_1h - rate_24h

    idx_6h_from = np.searchsorted(ev_ts_sec, cand_ts_sec - WINDOWS_SECONDS["6h"], side="right")
    idx_12h_from = np.searchsorted(ev_ts_sec, cand_ts_sec - 2 * WINDOWS_SECONDS["6h"], side="right")
    recent_rate = (idx_le - idx_6h_from) / 6.0
    prior_rate = (idx_6h_from - idx_12h_from) / 6.0
    out["rate_acceleration"] = recent_rate - prior_rate

    gaps_sec = np.diff(ev_ts_sec, prepend=ev_ts_sec[0] if len(ev_ts_sec) else 0)
    is_burst_event = (gaps_sec < 60).astype(np.int64)
    burst_cumsum = np.concatenate([[0], np.cumsum(is_burst_event)])
    idx_24h_from = np.searchsorted(ev_ts_sec, cand_ts_sec - WINDOWS_SECONDS["24h"], side="right")
    out["burst_count_24h"] = (burst_cumsum[idx_le] - burst_cumsum[idx_24h_from]).astype(float)

    gap_minutes = gaps_sec / 60.0
    roll = pd.Series(gap_minutes).rolling(20, min_periods=1)
    roll_mean = roll.mean().values
    roll_std = roll.std().fillna(0).values
    roll_min = roll.min().values
    roll_max = roll.max().values
    safe_idx = np.clip(idx_le - 1, 0, len(ev_ts_sec) - 1) if len(ev_ts_sec) else np.zeros(n_cand, dtype=int)
    has_history = idx_le > 0
    out["interarrival_mean"] = np.where(has_history, roll_mean[safe_idx], 0.0)
    out["interarrival_std"] = np.where(has_history, roll_std[safe_idx], 0.0)
    out["interarrival_min"] = np.where(has_history, roll_min[safe_idx], 0.0)
    out["interarrival_max"] = np.where(has_history, roll_max[safe_idx], 0.0)

    out["ewma_event_rate_1d"] = _ewma_daily_lookup(cand_ts_sec, ev_ts_sec, np.ones(len(ev_ts_sec)), 1.0)
    out["ewma_event_rate_7d"] = _ewma_daily_lookup(cand_ts_sec, ev_ts_sec, np.ones(len(ev_ts_sec)), 7.0)
    out["ewma_alarm_rate_1d"] = _ewma_daily_lookup(cand_ts_sec, ev_ts_sec, ev_alarm.astype(float), 1.0)
    out["ewma_alarm_rate_7d"] = _ewma_daily_lookup(cand_ts_sec, ev_ts_sec, ev_alarm.astype(float), 7.0)

    if numeric_mode:
        out["state_entropy_200ev"] = np.zeros(n_cand)
        out["n_unique_states_200ev"] = np.zeros(n_cand)
    else:
        codes, _ = pd.factorize(ev_value)
        entropy_series = _rolling_entropy(codes, window_events=200)
        unique_series = pd.Series(codes).rolling(200, min_periods=1).apply(lambda s: len(np.unique(s)), raw=True).values
        out["state_entropy_200ev"] = np.where(has_history, entropy_series[safe_idx], 0.0)
        out["n_unique_states_200ev"] = np.where(has_history, unique_series[safe_idx], 0.0)

    first_ts = ev_ts_sec[0] if len(ev_ts_sec) else 0
    observed_days = np.maximum((cand_ts_sec - first_ts) / 86400.0, 1.0)
    out["channel_event_prior"] = (idx_le + alpha * global_rates["event"]) / (observed_days + alpha)
    out["channel_alarm_prior"] = (alarm_cumsum[idx_le] + alpha * global_rates["alarm"]) / (observed_days + alpha)

    if len(fail_starts):
        fail_sec = fail_starts.astype("datetime64[s]").astype(np.int64)
        f_idx_le = np.searchsorted(fail_sec, cand_ts_sec, side="right")
        for wname, wsec in FAIL_WINDOWS_SECONDS.items():
            f_idx_from = np.searchsorted(fail_sec, cand_ts_sec - wsec, side="right")
            out[f"failures_{wname}"] = (f_idx_le - f_idx_from).astype(float)

        last_fail_idx = np.clip(f_idx_le - 1, 0, len(fail_sec) - 1)
        out["time_since_last_failure_days"] = np.where(
            f_idx_le > 0, (cand_ts_sec - fail_sec[last_fail_idx]) / 86400.0, -1.0
        )
        idx_2nd = np.clip(f_idx_le - 2, 0, len(fail_sec) - 1)
        out["days_since_last_2nd_failure"] = np.where(
            f_idx_le > 1, (cand_ts_sec - fail_sec[idx_2nd]) / 86400.0, -1.0
        )
        idx_3rd = np.clip(f_idx_le - 3, 0, len(fail_sec) - 1)
        out["days_since_last_3rd_failure"] = np.where(
            f_idx_le > 2, (cand_ts_sec - fail_sec[idx_3rd]) / 86400.0, -1.0
        )

        fail_gaps_days = np.diff(fail_sec) / 86400.0 if len(fail_sec) > 1 else np.array([])
        cum_median = np.zeros(len(fail_sec))
        cum_std = np.zeros(len(fail_sec))
        for k in range(1, len(fail_sec)):
            cum_median[k] = np.median(fail_gaps_days[:k])
            cum_std[k] = np.std(fail_gaps_days[:k]) if k > 1 else 0.0
        med_idx = np.clip(f_idx_le - 1, 0, max(len(fail_sec) - 1, 0))
        out["median_time_between_failures_days"] = np.where(f_idx_le > 1, cum_median[med_idx], 0.0)
        out["std_inter_failure_interval_days"] = np.where(f_idx_le > 2, cum_std[med_idx], 0.0)

        last_gap = np.concatenate([[0.0], fail_gaps_days])
        gap_idx = np.clip(f_idx_le - 1, 0, len(last_gap) - 1)
        out["last_inter_failure_interval_days"] = np.where(f_idx_le > 1, last_gap[gap_idx], 0.0)
        out["ratio_last_interval_to_historical_median"] = np.where(
            (f_idx_le > 2) & (out["median_time_between_failures_days"] > 0),
            out["last_inter_failure_interval_days"] / np.maximum(out["median_time_between_failures_days"], 1e-6),
            0.0,
        )

        out["historical_failure_rate"] = f_idx_le / observed_days
        out["channel_failure_prior"] = (f_idx_le + alpha * global_rates["failure"]) / (observed_days + alpha)
        out["ewma_failure_rate_7d"] = _ewma_daily_lookup(cand_ts_sec, fail_sec, np.ones(len(fail_sec)), 7.0)
        out["ewma_failure_rate_30d"] = _ewma_daily_lookup(cand_ts_sec, fail_sec, np.ones(len(fail_sec)), 30.0)
    else:
        for wname in FAIL_WINDOWS_SECONDS:
            out[f"failures_{wname}"] = np.zeros(n_cand)
        out["time_since_last_failure_days"] = np.full(n_cand, -1.0)
        out["days_since_last_2nd_failure"] = np.full(n_cand, -1.0)
        out["days_since_last_3rd_failure"] = np.full(n_cand, -1.0)
        out["median_time_between_failures_days"] = np.zeros(n_cand)
        out["std_inter_failure_interval_days"] = np.zeros(n_cand)
        out["last_inter_failure_interval_days"] = np.zeros(n_cand)
        out["ratio_last_interval_to_historical_median"] = np.zeros(n_cand)
        out["historical_failure_rate"] = np.zeros(n_cand)
        out["channel_failure_prior"] = np.full(n_cand, alpha * global_rates["failure"] / (observed_days.mean() + alpha) if n_cand else 0.0)
        out["ewma_failure_rate_7d"] = np.zeros(n_cand)
        out["ewma_failure_rate_30d"] = np.zeros(n_cand)

    last_event_idx = np.clip(idx_le - 1, 0, len(ev_ts_sec) - 1) if len(ev_ts_sec) else np.zeros(n_cand, dtype=int)
    out["time_since_last_event_hours"] = np.where(
        idx_le > 0, (cand_ts_sec - ev_ts_sec[last_event_idx]) / 3600.0, -1.0
    )

    if duty_cycle_mode:
        out.update(_duty_cycle_features(cand_ts_sec, ev_ts_sec, ev_value))

    return out


def compute_features(candidates, events, episodes, numeric_mode=False, duty_cycle_mode=False, global_rates=None):
    events = events.sort_values(["channel_id", "ts"]).reset_index(drop=True)
    episodes_by_channel = {
        cid: np.sort(g["episode_start"].values) for cid, g in episodes.groupby("channel_id", observed=True)
    } if len(episodes) else {}
    events_by_channel = {
        cid: (g["ts"].values, g["alarm_flag"].values, g["raw_value"].values)
        for cid, g in events.groupby("channel_id", sort=False, observed=True)
    }

    feature_frames = []
    for channel_id, cand_g in candidates.groupby("channel_id", sort=False, observed=True):
        ev_tuple = events_by_channel.get(channel_id)
        if ev_tuple is None:
            continue
        ev_ts, ev_alarm, ev_value = ev_tuple
        fail_starts = episodes_by_channel.get(channel_id, np.array([], dtype="datetime64[s]"))

        cand_ts = cand_g["ts"].values
        feats = _channel_features(cand_ts, ev_ts, ev_alarm, ev_value, fail_starts,
                                   numeric_mode=numeric_mode, duty_cycle_mode=duty_cycle_mode,
                                   global_rates=global_rates)
        feat_df = pd.DataFrame(feats, index=cand_g.index)
        feature_frames.append(feat_df)

    if not feature_frames:
        return candidates.iloc[0:0]

    all_feats = pd.concat(feature_frames)
    result = candidates.join(all_feats)
    return add_calendar_features(result)


def add_calendar_features(df):
    df["weekday"] = df["ts"].dt.weekday
    df["hour"] = df["ts"].dt.hour
    df["month"] = df["ts"].dt.month
    df["is_weekend"] = df["weekday"].isin([5, 6]).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    df["weekday_sin"] = np.sin(2 * np.pi * df["weekday"] / 7.0)
    df["weekday_cos"] = np.cos(2 * np.pi * df["weekday"] / 7.0)
    return df


def compute_features_single(cand_ts, ev_ts, ev_alarm, ev_value, fail_starts, numeric_mode=False,
                             duty_cycle_mode=False, global_rates=None):
    feats = _channel_features(cand_ts, ev_ts, ev_alarm, ev_value, fail_starts,
                               numeric_mode=numeric_mode, duty_cycle_mode=duty_cycle_mode,
                               global_rates=global_rates)
    df = pd.DataFrame(feats)
    df["ts"] = cand_ts
    return add_calendar_features(df)


FEATURE_COLUMNS = [
    "events_10m", "events_1h", "events_6h", "events_24h", "events_7d", "events_30d",
    "alarms_1h", "alarms_24h", "alarms_7d", "alarms_30d",
    "event_rate_delta", "rate_acceleration", "burst_count_24h",
    "interarrival_mean", "interarrival_std", "interarrival_min", "interarrival_max",
    "ewma_event_rate_1d", "ewma_event_rate_7d", "ewma_alarm_rate_1d", "ewma_alarm_rate_7d",
    "state_entropy_200ev", "n_unique_states_200ev",
    "failures_1d", "failures_3d", "failures_7d", "failures_14d", "failures_30d", "failures_90d",
    "historical_failure_rate", "median_time_between_failures_days", "std_inter_failure_interval_days",
    "last_inter_failure_interval_days", "ratio_last_interval_to_historical_median",
    "time_since_last_failure_days", "days_since_last_2nd_failure", "days_since_last_3rd_failure",
    "time_since_last_event_hours",
    "channel_event_prior", "channel_alarm_prior", "channel_failure_prior",
    "ewma_failure_rate_7d", "ewma_failure_rate_30d",
    "weekday", "hour", "month", "is_weekend", "hour_sin", "hour_cos", "weekday_sin", "weekday_cos",
]

DUTY_CYCLE_FEATURE_COLUMNS = [
    "time_in_current_state_hours", "mean_on_duration_hours", "mean_off_duration_hours",
    "max_on_duration_hours", "max_off_duration_hours",
    "transition_count_1h", "transition_count_6h", "transition_count_24h", "transition_count_7d",
    "on_off_cycles_1h", "on_off_cycles_6h", "on_off_cycles_24h", "on_off_cycles_7d",
]

NEIGHBOR_FEATURE_COLUMNS = [
    "neighbor_events_7d", "neighbor_alarms_7d",
    "neighbor_fraction_abnormal_7d", "neighbor_event_rate_delta",
]

WEATHER_FEATURE_COLUMNS = [
    "temp_mean", "temp_min", "precipitation", "humidity_mean", "pressure_mean",
]
