import numpy as np
import pandas as pd

from pipeline import tags

DETECTION_STATES = {
    "Датчик дыма": ["Обнаружен дым"],
    "Газовый датчик": ["Обнаружен газ"],
    "Датчик температуры": ["Температура ниже 3ºC", "Температура выше 40ºC"],
}
WINDOWS_MINUTES = (15, 30, 60)
MAINTENANCE_SERIES = {"Датчик дыма": (5, 10), "Газовый датчик": (3, 30)}
WORK_HOURS = (8, 18)


def detection_alarms(events, sensor_type, tag_by_channel):
    states = DETECTION_STATES[sensor_type]
    ev = events.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    grp = ev.groupby("channel_id", observed=True)
    in_state = ev["raw_value"].isin(states)
    change = in_state != grp["raw_value"].shift(1).isin(states)
    run_id = change.groupby(ev["channel_id"], observed=True).cumsum()
    nxt_ts = grp["ts"].shift(-1)
    run_end = nxt_ts.groupby([ev["channel_id"], run_id], observed=True).transform("last")
    dwell = (run_end - ev["ts"]).dt.total_seconds() / 60.0
    alarm = in_state & (ev["alarm_flag"] == 1)
    out = ev.loc[alarm, ["channel_id", "ts"]].copy()
    out["dwell_minutes"] = dwell[alarm].values
    out["sensor_type"] = sensor_type
    tag = out["channel_id"].astype(str).map(tag_by_channel)
    group = tag.map(lambda t: tags.tag_group_key(t) if isinstance(t, str) else None)
    out["tag_group"] = np.where(group.notna(), group.astype(str), out["channel_id"].astype(str))
    return out.reset_index(drop=True)


def _count_in_window(times_by_key, keys, ts, minutes):
    out = np.zeros(len(ts), dtype=np.int64)
    w = np.timedelta64(int(minutes * 60), "s")
    df = pd.DataFrame({"k": keys, "i": np.arange(len(ts))})
    for k, g in df.groupby("k", sort=False):
        arr = times_by_key.get(k)
        if arr is None:
            continue
        idx = g["i"].values
        t = ts[idx]
        out[idx] = np.searchsorted(arr, t + w, side="right") - np.searchsorted(arr, t, side="right")
    return out


def corroboration_labels(alarms, minutes):
    ts = alarms["ts"].values
    ch = alarms["channel_id"].astype(str).values
    grp = alarms["tag_group"].astype(str).values
    by_ch = {k: np.sort(g["ts"].values) for k, g in alarms.assign(_c=ch).groupby("_c")}
    by_grp = {k: np.sort(g["ts"].values) for k, g in alarms.assign(_g=grp).groupby("_g")}
    same_channel = _count_in_window(by_ch, ch, ts, minutes)
    same_group = _count_in_window(by_grp, grp, ts, minutes)
    repeat = same_channel > 0
    neighbor = (same_group - same_channel) > 0
    sustained = alarms["dwell_minutes"].values >= minutes
    return pd.DataFrame({"repeat": repeat, "neighbor": neighbor, "sustained": sustained,
                         "corroborated": repeat | neighbor | sustained}, index=alarms.index)


def group_history_features(alarms):
    ts = alarms["ts"].values
    ch = alarms["channel_id"].astype(str).values
    grp = alarms["tag_group"].astype(str).values
    by_ch = {k: np.sort(g["ts"].values) for k, g in alarms.assign(_c=ch).groupby("_c")}
    by_grp = {k: np.sort(g["ts"].values) for k, g in alarms.assign(_g=grp).groupby("_g")}
    out = {}
    for name, hours in (("1h", 1), ("24h", 24), ("7d", 168)):
        w = np.timedelta64(int(hours * 3600), "s")
        cc = np.zeros(len(ts)); gc = np.zeros(len(ts))
        for arr_map, keys, dest in ((by_ch, ch, cc), (by_grp, grp, gc)):
            df = pd.DataFrame({"k": keys, "i": np.arange(len(ts))})
            for k, g in df.groupby("k", sort=False):
                arr = arr_map[k]; idx = g["i"].values; t = ts[idx]
                dest[idx] = np.searchsorted(arr, t, side="left") - np.searchsorted(arr, t - w, side="left")
        out[f"alarm_ch_prev_{name}"] = cc
        out[f"alarm_grp_prev_{name}"] = gc - cc
    return pd.DataFrame(out, index=alarms.index)


def maintenance_series(alarms, object_by_channel):
    objects = alarms["channel_id"].astype(str).map(object_by_channel)
    work = ((alarms["ts"].dt.weekday < 5) & alarms["ts"].dt.hour.between(WORK_HOURS[0], WORK_HOURS[1] - 1)).values
    flag = np.zeros(len(alarms), dtype=bool)
    for (sensor, _), group in alarms.assign(_object=objects).dropna(subset=["_object"]).groupby(["sensor_type", "_object"]):
        if sensor not in MAINTENANCE_SERIES:
            continue
        count, minutes = MAINTENANCE_SERIES[sensor]
        group = group.sort_values("ts", kind="stable")
        ts = group["ts"].values
        channels = group["channel_id"].astype(str).values
        ends = np.searchsorted(ts, ts + np.timedelta64(minutes, "m"), side="right")
        series = np.zeros(len(group), dtype=bool)
        for start, end in enumerate(ends):
            if end - start >= count and len(set(channels[start:end])) >= count:
                series[start:end] = True
        flag[alarms.index.get_indexer(group.index)] = series
    return flag & work
