import numpy as np
import pandas as pd
import pyarrow.dataset as ds

from pipeline import config, extract, tags

STREAMS = {
    "people": [("Датчик движения", "Обнаружено движение"), ("КД Дверь", "Не замкнут"), ("КД Люк", "Не замкнут")],
    "power": [("Состояние фазы", "Обесточен")],
    "smoke": [("Датчик дыма", "Обнаружен дым")],
}
WINDOWS_HOURS = (1, 24, 168)


def _cache_path(sensor_type):
    return f"{config.ROOT}/analysis/ml_ready/cache/events_{sensor_type.replace(' ', '_')}.parquet"


def _stream_events(pairs):
    parts = []
    for sensor_type, state in pairs:
        table = ds.dataset(_cache_path(sensor_type)).to_table(
            columns=["channel_id", "ts", "tag"], filter=ds.field("raw_value") == state)
        parts.append(table.to_pandas())
    events = pd.concat(parts, ignore_index=True)
    events["channel_id"] = events["channel_id"].astype(str)
    return events


def locations():
    dictionary = extract.channel_dictionary()
    channel = dictionary["ид_канала_данных"].astype(str)
    section = dictionary["тег_инженерной_системы"].map(lambda t: tags.tag_group_key(t) if isinstance(t, str) else None)
    objects = dictionary["ид_объект"] if "ид_объект" in dictionary else dictionary["тег_инженерной_системы"].str.split("-").str[0]
    return dict(zip(channel, objects.astype(str), strict=True)), dict(zip(channel, section, strict=True))


def _counts(times_by_key, keys, ts):
    result = {f"{hours}h": np.zeros(len(ts)) for hours in WINDOWS_HOURS}
    since = np.full(len(ts), np.nan)
    frame = pd.DataFrame({"key": keys, "row": np.arange(len(ts))}).dropna(subset=["key"])
    for key, group in frame.groupby("key", sort=False):
        times = times_by_key.get(key)
        if times is None:
            continue
        rows = group["row"].to_numpy()
        t = ts[rows]
        upto = np.searchsorted(times, t, side="right")
        for hours in WINDOWS_HOURS:
            start = np.searchsorted(times, t - np.timedelta64(hours, "h"), side="right")
            result[f"{hours}h"][rows] = upto - start
        last = np.where(upto > 0, times[np.maximum(upto - 1, 0)], np.datetime64("NaT"))
        since[rows] = (t - last) / np.timedelta64(1, "h")
    return result, since


def features(candidates, object_of, section_of, streams=None):
    ts = candidates["ts"].to_numpy(dtype="datetime64[ns]")
    channels = candidates["channel_id"].astype(str)
    keys = {"object": channels.map(object_of).to_numpy(), "section": channels.map(section_of).to_numpy()}
    out = {}
    for name, pairs in (streams or STREAMS).items():
        events = _stream_events(pairs)
        for level, key_of in (("object", object_of), ("section", section_of)):
            event_keys = events["channel_id"].map(key_of)
            grouped = events.assign(_key=event_keys).dropna(subset=["_key"]).groupby("_key")["ts"]
            times_by_key = {key: np.sort(group.to_numpy(dtype="datetime64[ns]")) for key, group in grouped}
            counts, since = _counts(times_by_key, keys[level], ts)
            for window, values in counts.items():
                out[f"ctx_{name}_{level}_{window}"] = values
            out[f"ctx_{name}_{level}_hours_since"] = since
    return pd.DataFrame(out, index=candidates.index)
