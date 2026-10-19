import json
import os
import sys
import time

import numpy as np
import pandas as pd

from pipeline import artifacts, context, incidents, recipes
from pipeline.formal import metrics as fm
from run_object_level import INCIDENT_SOURCE, feature_sets, frames, state_table, summary
from run_refit_study import EMBARGO

YEAR = 2025
OUTPUT = os.path.join(os.path.dirname(__file__), "object_selection.json")
CHANNEL_CACHE = os.path.join(os.path.dirname(__file__), "cache")
VARIANTS = ("channel", "history", "state", "rule", "blend")
PARAMS = dict(n_estimators=300, learning_rate=0.03, num_leaves=15, min_child_samples=50, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7, n_jobs=4)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def daily(scored, events, start, end, horizon=24):
    rows = []
    for day in pd.date_range(start, end, freq="D"):
        window = scored.loc[(scored["ts"] >= day - pd.Timedelta(hours=24)) & (scored["ts"] < day)]
        if window.empty:
            continue
        score = window.groupby("channel_id").tail(1).groupby("object")["score"].max()
        future = events.loc[(events["t0"] >= day) & (events["t0"] < day + pd.Timedelta(hours=horizon)), "object"]
        rows.append(pd.DataFrame({"key": score.index, "day": day, "channel": score.values,
                                  "target": score.index.isin(set(future)).astype(int)}))
    return pd.concat(rows, ignore_index=True)


def channel_scores(name, frame, object_of):
    model, meta = artifacts.load_artifact(name)
    columns = meta["feature_columns"]
    years = [int(y) for y in meta["training_period"]["train_years"].split("-")]
    span = years[1] - years[0] + 1
    train = (frame["ts"] < pd.Timestamp(f"{YEAR}-01-01") - EMBARGO) & (frame["ts"].dt.year >= YEAR - span)
    staging = recipes.fit(recipes.recipe_of(meta), frame.loc[train, columns], frame.loc[train, "target"])
    test = frame.loc[frame["ts"].dt.year == YEAR, ["channel_id", "ts", *columns]]
    scored = test[["channel_id", "ts"]].assign(score=staging.predict_proba(test[columns]))
    scored["channel_id"] = scored["channel_id"].astype(str)
    scored["object"] = scored["channel_id"].map(object_of)
    return scored.dropna(subset=["object"]).sort_values("ts")


def tuned(kind, variant):
    path = os.path.join(os.path.dirname(__file__), "object_tuning.json")
    if not os.path.exists(path):
        return dict(PARAMS)
    best = json.load(open(path, encoding="utf-8")).get(kind, {}).get(variant, {}).get("best")
    return {**PARAMS, **{k: best[k] for k in ("num_leaves", "min_child_samples", "n_estimators")}} if best else dict(PARAMS)


def history_scores(table, kind):
    import lightgbm as lgb

    history, every = feature_sets(table)
    train = table["day"] < pd.Timestamp(f"{YEAR}-01-01") - pd.Timedelta(days=1)
    test = table.loc[table["day"].dt.year == YEAR]
    y = table.loc[train, f"y_{kind}"].astype(int)
    out = test[["object", "day"]].assign(rule=test[f"{kind}_7d"] + test[f"{kind}_30d"] / 100.0)
    for name, columns in (("history", history), ("state", every)):
        model = lgb.LGBMClassifier(**tuned(kind, name)).fit(table.loc[train, columns], y)
        out[name] = model.predict_proba(test[columns])[:, 1]
    return out


def channel_daily(kind, registry, object_of):
    path = os.path.join(CHANNEL_CACHE, f"object_selection_{kind}_{YEAR}.parquet")
    if os.path.exists(path):
        return pd.read_parquet(path)
    name, frame, _ = next(frames([INCIDENT_SOURCE[kind]]))
    channel = channel_scores(name, frame, object_of)
    del frame
    base = daily(channel, registry[kind], f"{YEAR}-01-02", f"{YEAR}-12-30")
    os.makedirs(CHANNEL_CACHE, exist_ok=True)
    base.to_parquet(path)
    return base


def main():
    kinds = sys.argv[1:] or list(INCIDENT_SOURCE)
    object_of = context.locations()[0]
    registry = incidents.registry(object_of)
    table = state_table(registry, object_of)
    report = {"year": YEAR, "unit": "object-day", "variants": {}}
    if os.path.exists(OUTPUT):
        report = json.load(open(OUTPUT, encoding="utf-8"))
    for kind in kinds:
        source = INCIDENT_SOURCE[kind]
        base = channel_daily(kind, registry, object_of)
        merged = base.merge(history_scores(table, kind).rename(columns={"object": "key"}), on=["key", "day"])
        merged["blend"] = merged["channel"].rank(pct=True) + merged["history"].rank(pct=True)
        result = {}
        for variant in VARIANTS:
            result[variant] = {k: v for k, v in summary(merged.assign(score=merged[variant])).items() if k != "curve"}
        best = max(result, key=lambda v: result[v]["avg_precision"] if v != "rule" else -1)
        report["variants"][kind] = {"source_model": source, "selected": best, "params": {v: tuned(kind, v) for v in ("history", "state")}, **result}
        log(f"{kind}: " + ", ".join(f"{v} AP {result[v]['avg_precision']} top3 {result[v]['top_k']['3']}" for v in result) + f" -> {best}")
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
