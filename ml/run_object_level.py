import json
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments.run_location_day import daily, starts_of
from pipeline import artifacts, config, context, extract, incidents, object_risk
from pipeline.formal import metrics as fm
from pipeline.targets import discovery, state_target
from run_refit_study import frames as refit_frames

OUTPUT = os.path.join(config.ROOT, "results", "object_level.json")
SELECTION = os.path.join(config.ROOT, "experiments", "object_selection.json")
MODELS = {
    "phase_24h": ("Потеря питания", "power_loss"),
    "pump_72h": ("Отказ насоса, 72 ч", "flooding"),
    "pump_24h": ("Отказ насоса, 24 ч", "flooding"),
    "fan_72h": ("Отказ вентилятора, 72 ч", "ventilation"),
    "fan_24h": ("Отказ вентилятора, 24 ч", "ventilation"),
    "flood_24h": ("Затопление камеры", "flooding"),
    "smoke_24h": ("Неисправность дымового датчика", "fire"),
    "smoke_alarm_24h": ("Срабатывание дымового датчика", "fire"),
}
INCIDENT_SOURCE = {"fire": "smoke_alarm_24h", "flood": "flood_24h", "power": "phase_24h"}
CURVE_K = range(1, 16)
TEST_START, TEST_END = pd.Timestamp("2026-01-02"), pd.Timestamp("2026-06-30")
HISTORY_WINDOWS = (1, 7, 30, 90)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def topk(frame, k):
    ranked = frame.sort_values(["day", "score"], ascending=[True, False]).groupby("day").head(k)
    days = frame["day"].nunique()
    hits = int(ranked["target"].sum())
    positives = int(frame["target"].sum())
    return {"top_k": k, "precision": round(hits / max(len(ranked), 1), 4),
            "recall": round(hits / positives, 4) if positives else None,
            "alerts_per_day": round(len(ranked) / days, 2)}


def summary(frame):
    frontier = fm.frontier_metrics(frame["target"].to_numpy(), frame["score"].to_numpy())
    curve = [topk(frame, k) for k in CURVE_K]
    base = float(frame["target"].mean())
    return {
        "objects_per_day": round(len(frame) / frame["day"].nunique(), 1),
        "days": int(frame["day"].nunique()),
        "base_rate": round(base, 4),
        "avg_precision": round(float(frontier["pr_auc"]), 4),
        "roc_auc": round(float(frontier["roc_auc"]), 4),
        "lift_top3": round(curve[2]["precision"] / base, 2) if base else None,
        "top_k": {str(k): curve[k - 1]["precision"] for k in (3, 5, 10)},
        "recall_top_k": {str(k): curve[k - 1]["recall"] for k in (3, 5, 10)},
        "recall_at_precision_0_7": round(float(frontier["recall_at_precision_0.7"]), 4),
        "precision_at_recall_0_5": round(float(frontier["precision_at_recall_0.5"]), 4),
        "curve": curve,
    }


def frames(names):
    yield from refit_frames(names)
    if "smoke_alarm_24h" in names:
        events = extract.extract_events(config.SENSOR_ALIASES["smoke"])
        frame = state_target.build_frame(events, "Обнаружен дым", horizons=(24,), include_lockbox=True)[0]
        yield "smoke_alarm_24h", frame.rename(columns={"y24": "target"}), 24


def model_starts(name, section_of, object_of):
    if name != "smoke_alarm_24h":
        return starts_of(name, section_of, object_of)
    episodes = discovery.state_episodes(extract.extract_events(config.SENSOR_ALIASES["smoke"]), "Обнаружен дым")
    starts = episodes[["channel_id", "episode_start"]].assign(channel_id=lambda f: f["channel_id"].astype(str))
    return starts.assign(channel=starts["channel_id"], section=starts["channel_id"].map(section_of), object=starts["channel_id"].map(object_of))


def scored_channels(names, object_of):
    out = {}
    for name, frame, horizon in frames(names):
        model, meta = artifacts.load_artifact(name)
        recent = frame.loc[frame["ts"].dt.year == 2026, ["channel_id", "ts", *meta["feature_columns"]]].copy()
        recent["channel_id"] = recent["channel_id"].astype(str)
        scored = recent[["channel_id", "ts"]].assign(score=model.predict_proba(recent[meta["feature_columns"]])).sort_values("ts")
        scored["object"] = scored["channel_id"].map(object_of)
        out[name] = (scored.dropna(subset=["object"]), horizon)
        log(f"scored {name}: {len(scored)} candidates")
    return out


def incident_starts(frame):
    return pd.DataFrame({"object": frame["object"].astype(str), "episode_start": frame["t0"]})


def panel(registry, objects):
    days = pd.date_range("2019-01-08", TEST_END, freq="D")
    objects = sorted(objects)
    index = pd.MultiIndex.from_product([objects, days], names=["object", "day"])
    out = pd.DataFrame(index=index).reset_index()
    out["month"] = out["day"].dt.month
    out["weekday"] = out["day"].dt.weekday
    n_obj, n_days = len(objects), len(days)
    position = np.arange(n_days)
    for kind, frame in registry.items():
        counts = frame.assign(day=frame["t0"].dt.normalize()).groupby(["object", "day"]).size()
        grid = counts.reindex(index, fill_value=0).to_numpy(dtype=float).reshape(n_obj, n_days)
        before = np.concatenate([np.zeros((n_obj, 1)), np.cumsum(grid, axis=1)[:, :-1]], axis=1)
        for w in HISTORY_WINDOWS:
            lagged = np.concatenate([np.zeros((n_obj, w)), before[:, :-w]], axis=1) if w < n_days else np.zeros_like(before)
            out[f"{kind}_{w}d"] = (before - lagged).ravel()
        last = np.maximum.accumulate(np.where(grid > 0, position, -1), axis=1)
        last = np.concatenate([np.full((n_obj, 1), -1), last[:, :-1]], axis=1)
        out[f"{kind}_days_since"] = np.where(last >= 0, position - last, 9999).ravel().astype(float)
        out[f"y_{kind}"] = (grid > 0).ravel()
    return out


def feature_sets(table):
    every = [c for c in table.columns if not c.startswith("y_") and c not in ("object", "day")]
    state = [c for c in every if c.startswith(tuple(f"{p}_" for p in object_risk.STATE_PREFIX.values()))]
    return [c for c in every if c not in state], every


def state_table(registry, object_of):
    objects = sorted(set(object_of.values()))
    table = panel(registry, objects)
    events = {sensor: object_risk.state_events(sensor) for sensor in object_risk.STATES}
    states = object_risk.state_panel(events, object_of, objects, pd.DatetimeIndex(sorted(table["day"].unique())))
    return table.merge(states, on=["object", "day"], how="left")


def history_model(table, kind, features, params=None):
    params = params or dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8,
                            subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7)
    y = table[f"y_{kind}"].astype(int)
    select_train = table["day"] < pd.Timestamp("2024-12-31")
    select_test = table["day"].dt.year == 2025
    selection = lgb.LGBMClassifier(**params).fit(table.loc[select_train, features], y[select_train])
    ap_2025 = fm.frontier_metrics(y[select_test].to_numpy(), selection.predict_proba(table.loc[select_test, features])[:, 1])["pr_auc"]
    final_train = table["day"] < pd.Timestamp("2025-12-31")
    final = lgb.LGBMClassifier(**params).fit(table.loc[final_train, features], y[final_train])
    test = table.loc[(table["day"] >= TEST_START) & (table["day"] <= TEST_END - pd.Timedelta(days=1))]
    return test.assign(score=final.predict_proba(test[features])[:, 1], target=y.loc[test.index].to_numpy()), round(float(ap_2025), 4)


def append_object_models(report):
    variant_key = {"history": "history_model", "state": "state_model", "blend": "blend"}
    report["models"] = [model for model in report["models"] if not model["id"].startswith("object_")]
    for kind, entry in report["incidents"].items():
        name = f"object_{kind}_24h"
        if not os.path.exists(os.path.join(artifacts.artifact_dir(name), "meta.json")):
            continue
        variant = artifacts.load_artifact(name)[1]["model_config"]["variant"]
        scenario = object_risk.KINDS[kind][0]
        report["models"].append({"id": name, "label": f"{entry['label']}, модель объекта", "scenario": scenario,
                                 "horizon_hours": 24, **entry["variants"][variant_key[variant]]})
    return report


def selected_params(kind):
    if not os.path.exists(SELECTION):
        return {}
    return json.load(open(SELECTION, encoding="utf-8"))["variants"].get(kind, {}).get("params", {})


def rule_baseline(table, kind):
    test = table.loc[(table["day"] >= TEST_START) & (table["day"] <= TEST_END - pd.Timedelta(days=1))]
    score = test[f"{kind}_7d"] + test[f"{kind}_30d"] / 100.0
    return test.assign(score=score.to_numpy(), target=test[f"y_{kind}"].astype(int).to_numpy())


def main():
    names = sys.argv[1:] or list(MODELS)
    object_of, section_of = context.locations()
    registry = incidents.registry(object_of)
    report = {"period": "2026H1", "unit": "object-day", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "note": "Утренний список: в полночь берётся последняя оценка каждого канала за сутки, объект оценивается максимумом по своим каналам; попадание — начало события на объекте в горизонте модели.",
              "models": [], "incidents": {}}
    scored = scored_channels(sorted(set(names) | set(INCIDENT_SOURCE.values())), object_of)
    for name in names:
        if name not in scored:
            continue
        frame, horizon = scored[name]
        starts = model_starts(name, section_of, object_of)
        result = summary(daily(frame, starts.dropna(subset=["object"]), "object", horizon))
        label, scenario = MODELS[name]
        report["models"].append({"id": name, "label": label, "scenario": scenario, "horizon_hours": horizon, **result})
        log(f"{name}: top3 {result['top_k']['3']} base {result['base_rate']} R@P0.7 {result['recall_at_precision_0_7']}")

    table = state_table(registry, object_of)
    history_columns, state_columns = feature_sets(table)
    rules = incidents.rules()
    for kind, source in INCIDENT_SOURCE.items():
        events = registry[kind]
        entry = {"label": rules[kind]["label"], "rule": rules[kind]["rule"], "source_model": source,
                 "per_year": {str(y): int(c) for y, c in events["t0"].dt.year.value_counts().sort_index().items()},
                 "objects": int(events["object"].nunique()), "variants": {}}
        frame, horizon = scored[source]
        channel_max = daily(frame, incident_starts(events), "object", 24)
        entry["variants"]["channel_model"] = summary(channel_max)
        params = selected_params(kind)
        history, ap_2025 = history_model(table, kind, history_columns, params.get("history"))
        active = history.loc[history["object"].isin(set(channel_max["key"]))]
        entry["variants"]["history_model"] = {**summary(active.rename(columns={"object": "key"})), "avg_precision_2025": ap_2025}
        state, state_2025 = history_model(table, kind, state_columns, params.get("state"))
        state = state.loc[state["object"].isin(set(channel_max["key"]))]
        entry["variants"]["state_model"] = {**summary(state.rename(columns={"object": "key"})), "avg_precision_2025": state_2025}
        entry["variants"]["rule_7d"] = summary(rule_baseline(table, kind).pipe(lambda f: f.loc[f["object"].isin(set(channel_max["key"]))]))
        merged = channel_max.merge(active[["object", "day", "score"]].rename(columns={"object": "key", "score": "history"}), on=["key", "day"])
        merged["score"] = merged["score"].rank(pct=True) + merged["history"].rank(pct=True)
        entry["variants"]["blend"] = summary(merged)

        if os.path.exists(SELECTION):
            entry["selected_2025"] = json.load(open(SELECTION, encoding="utf-8"))["variants"].get(kind, {}).get("selected")
        report["incidents"][kind] = entry
        log(f"{kind}: " + ", ".join(f"{v} AP {entry['variants'][v]['avg_precision']} top3 {entry['variants'][v]['top_k']['3']}" for v in entry["variants"]))
    append_object_models(report)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=1)
    log(f"written {OUTPUT}")


if __name__ == "__main__":
    main()
