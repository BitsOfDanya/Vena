import os

import numpy as np
import pandas as pd

from pipeline import artifacts, calibration, incidents

KINDS = {
    "power": ("power_loss", "object_power_24h", "phase_24h"),
    "flood": ("flooding", "object_flood_24h", "flood_24h"),
    "fire": ("fire", "object_fire_24h", "smoke_alarm_24h"),
}
WINDOWS = (1, 7, 30, 90)
NOWCAST = "object_flood_6h"
NOWCAST_WINDOWS = (24, 168, 720)
SENSORS = {"fire": "Датчик дыма", "flood": "Состояние насоса", "power": "Состояние фазы"}
STATES = {
    "Состояние фазы": ("Обесточен", "Неисправен", "Неопределен"),
    "Состояние насоса": ("Затоплен", "Неисправен", "Обесточен", "Включен"),
    "Датчик дыма": ("Обнаружен дым", "Неисправен", "Неопределен"),
}
STATE_WINDOWS = (1, 7, 30)
STATE_PREFIX = {"Состояние фазы": "phase", "Состояние насоса": "pump", "Датчик дыма": "smoke"}


def state_events(sensor, since=None):
    frame = incidents._events(sensor, list(STATES[sensor]))
    return frame if since is None else frame.loc[frame["ts"] >= since]


def state_panel(events_by_sensor, object_of, objects, days):
    days = pd.DatetimeIndex(days).normalize()
    span = pd.date_range(days[0] - pd.Timedelta(days=max(STATE_WINDOWS)), days[-1], freq="D")
    objects = list(objects)
    index = {o: i for i, o in enumerate(objects)}
    offset = len(span) - len(days)
    out = {}
    for sensor, states in STATES.items():
        events = events_by_sensor.get(sensor)
        prefix = STATE_PREFIX[sensor]
        if events is None:
            events = pd.DataFrame({"channel_id": [], "ts": pd.to_datetime([]), "raw_value": []})
        events = events.loc[events["raw_value"].isin(states), ["channel_id", "ts", "raw_value"]]
        events = events.assign(object=events["channel_id"].astype(str).map(object_of), day=events["ts"].dt.normalize())
        events = events.loc[events["object"].isin(index) & (events["day"] >= span[0]) & (events["day"] <= span[-1])]
        rows = events["object"].map(index).to_numpy()
        cols = ((events["day"] - span[0]) / pd.Timedelta(days=1)).to_numpy().astype(int)
        for state in states:
            mask = (events["raw_value"] == state).to_numpy()
            grid = np.zeros((len(objects), len(span) + 1))
            np.add.at(grid, (rows[mask], cols[mask] + 1), 1)
            before = np.cumsum(grid, axis=1)[:, :-1]
            for w in STATE_WINDOWS:
                lagged = np.concatenate([np.zeros((len(objects), w)), before[:, :-w]], axis=1)
                out[f"{prefix}_{state}_{w}d"] = (before - lagged)[:, offset:]
        channels = events.groupby(["object", "day"])["channel_id"].nunique()
        grid = np.zeros((len(objects), len(span) + 1))
        if len(channels):
            keys = channels.index.to_frame(index=False)
            grid[keys["object"].map(index).to_numpy(), ((keys["day"] - span[0]) / pd.Timedelta(days=1)).to_numpy().astype(int) + 1] = channels.to_numpy()
        out[f"{prefix}_channels_1d"] = grid[:, :-1][:, offset:]
    frame = pd.DataFrame({"object": np.repeat(objects, len(days)), "day": np.tile(days.values, len(objects))})
    for name, values in out.items():
        frame[name] = values.ravel()
    return frame


def available():
    return [kind for kind, (_, name, _) in KINDS.items() if os.path.exists(os.path.join(artifacts.artifact_dir(name), "meta.json"))]


def registry_from(events_by_sensor, object_of):
    columns = ["channel_id", "ts", "raw_value"]
    empty = pd.DataFrame({"channel_id": pd.Series(dtype=str), "ts": pd.Series(dtype="datetime64[ns]"), "raw_value": pd.Series(dtype=str)})
    frames = {kind: events_by_sensor.get(sensor, empty)[columns] for kind, sensor in SENSORS.items()}
    return {
        "fire": incidents.fire_incidents(object_of, frames["fire"], empty),
        "flood": incidents.flood_incidents(object_of, frames["flood"].sort_values(["channel_id", "ts"], kind="stable")),
        "power": incidents.power_incidents(object_of, frames["power"]),
    }


def reference_path(name):
    return os.path.join(artifacts.artifact_dir(name), "reference.npz")


def ecdf(values, reference):
    return np.searchsorted(reference, np.asarray(values, dtype=float), side="right") / len(reference)


def channel_by_object(predictions, object_of):
    out = {}
    for row in predictions or []:
        obj = object_of.get(str(row.get("channel_id")))
        raw = row.get("raw_score")
        if obj is None or raw is None:
            continue
        key = (row["model_id"], obj)
        out[key] = max(out.get(key, raw), raw)
    return out


def features(registry, objects, day):
    day = pd.Timestamp(day).normalize()
    out = pd.DataFrame({"object": objects})
    out["month"] = day.month
    out["weekday"] = day.weekday()
    for kind in ("fire", "flood", "power"):
        frame = registry.get(kind)
        days = frame.assign(day=frame["t0"].dt.normalize()) if frame is not None and len(frame) else None
        for w in WINDOWS:
            if days is None:
                out[f"{kind}_{w}d"] = 0.0
                continue
            window = days.loc[(days["day"] >= day - pd.Timedelta(days=w)) & (days["day"] < day)]
            counts = window.groupby("object").size()
            out[f"{kind}_{w}d"] = out["object"].map(counts).fillna(0).astype(float)
        if days is None:
            out[f"{kind}_days_since"] = 9999.0
            continue
        last = days.loc[days["day"] < day].groupby("object")["day"].max()
        since = (day - out["object"].map(last)).dt.days
        out[f"{kind}_days_since"] = since.fillna(9999).astype(float)
    return out


def nowcast_features(flood, objects, now, confirm_minutes):
    now = pd.Timestamp(now)
    out = pd.DataFrame({"object": objects, "hour": now.hour, "weekday": now.weekday(), "month": now.month})
    known = pd.Series(dtype="datetime64[ns]") if flood is None or flood.empty else flood["t0"] + pd.Timedelta(minutes=confirm_minutes)
    frame = pd.DataFrame({"object": [] if flood is None or flood.empty else flood["object"].astype(str), "known": known})
    frame = frame.loc[frame["known"] < now]
    for w in NOWCAST_WINDOWS:
        counts = frame.loc[frame["known"] >= now - pd.Timedelta(hours=w)].groupby("object").size()
        out[f"incidents_{w}h"] = out["object"].map(counts).fillna(0).astype(float)
    last = frame.groupby("object")["known"].max()
    out["hours_since_incident"] = ((now - out["object"].map(last)) / pd.Timedelta(hours=1)).fillna(1e5).astype(float)
    return out


def nowcast(registry, now, objects):
    if not os.path.exists(os.path.join(artifacts.artifact_dir(NOWCAST), "meta.json")):
        return None, None
    model, meta = artifacts.load_artifact(NOWCAST)
    table = nowcast_features(registry.get("flood"), objects, now, incidents.rules()["flood"]["window_minutes"])
    raw = model.predict_proba(table[meta["feature_columns"]])[:, 1]
    calibrator = artifacts.load_calibrator(NOWCAST)
    probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0.0, 1.0) if calibrator is not None else raw
    places = {obj: place for place, obj in enumerate(table["object"].iloc[np.argsort(-raw, kind="stable")], start=1)}
    test = meta["metrics_snapshot"].get("test_2026h1", {})
    summary = {"model_id": NOWCAST, "horizon_hours": meta["model_config"]["horizon_hours"], "period": "2026H1",
               "share_top3": test.get("share_top3"), "rule_share_top3": test.get("rule_share_top3"),
               "objects": test.get("objects"), "avg_precision": test.get("avg_precision"), "base_rate": test.get("base_rate")}
    return {obj: (round(float(p), 4), places[obj]) for obj, p in zip(table["object"], probability)}, summary


def score(registry, now, object_of, channel=None, events=None, kinds=None, recent_flood=None):
    day = pd.Timestamp(now).normalize()
    objects = sorted(set(object_of.values()))
    table = features(registry, objects, day)
    channel = channel or {}
    rows, meta_out = [], {}
    for kind in available():
        if kinds is not None and kind not in kinds:
            continue
        scenario, name, source = KINDS[kind]
        model, meta = artifacts.load_artifact(name)
        calibrator = artifacts.load_calibrator(name)
        variant = meta["model_config"]["variant"]
        if variant == "state" and "phase_channels_1d" not in table:
            if events is None:
                events = {sensor: state_events(sensor, since=day - pd.Timedelta(days=max(STATE_WINDOWS) + 1)) for sensor in STATES}
            states = state_panel(events, object_of, objects, pd.DatetimeIndex([day]))
            table = table.merge(states.drop(columns="day"), on="object", how="left")
        raw = model.predict_proba(table[meta["feature_columns"]])[:, 1]
        channel_raw = np.array([channel.get((source, obj), np.nan) for obj in table["object"]], dtype=float)
        if variant == "blend":
            reference = np.load(reference_path(name))
            raw = ecdf(np.nan_to_num(channel_raw, nan=-1.0), reference["channel"]) + ecdf(raw, reference["history"])
        probability = np.clip(calibration.apply_isotonic(calibrator, raw), 0.0, 1.0) if calibrator is not None else raw
        order = np.lexsort((-probability, -raw))
        for rank, i in enumerate(order, start=1):
            rows.append({
                "object_id": str(table["object"].iloc[i]),
                "scenario": scenario,
                "model_id": name,
                "probability": round(float(probability[i]), 4),
                "rank": rank,
                "horizon_hours": 24,
                "day": day.date().isoformat(),
                "history": {
                    "1d": int(table[f"{kind}_1d"].iloc[i]),
                    "7d": int(table[f"{kind}_7d"].iloc[i]),
                    "30d": int(table[f"{kind}_30d"].iloc[i]),
                    "90d": int(table[f"{kind}_90d"].iloc[i]),
                    "days_since": None if table[f"{kind}_days_since"].iloc[i] >= 9999 else int(table[f"{kind}_days_since"].iloc[i]),
                },
                "channel_score": None if np.isnan(channel_raw[i]) else round(float(channel_raw[i]), 4),
            })
        if kind == "flood":
            short, summary = nowcast(registry if recent_flood is None else {"flood": recent_flood}, now, objects)
            if short is not None:
                for row in rows:
                    if row["model_id"] == name and row["object_id"] in short:
                        row["probability_6h"], row["rank_6h"] = short[row["object_id"]]
        test = meta["metrics_snapshot"].get("test_2026h1", {})
        meta_out[name] = {
            "label": meta["model_config"]["label"],
            "scenario": scenario,
            "rule": meta["model_config"]["rule"],
            "source_model": source,
            "variant": meta["model_config"]["variant"],
            "period": "2026H1",
            "precision_top3": test.get("top3"),
            "recall_top3": test.get("recall_top3"),
            "base_rate": test.get("base_rate"),
            "avg_precision": test.get("avg_precision"),
        }
        if kind == "flood" and short is not None:
            meta_out[name]["nowcast"] = summary
    return rows, meta_out
