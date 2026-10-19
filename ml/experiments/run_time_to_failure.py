import json
import os
import sys
import time

import lightgbm as lgb
import numpy as np
import pandas as pd

from pipeline import artifacts, config
from pipeline.experiments import DeviceContext

OUTPUT = os.path.join(os.path.dirname(__file__), "time_to_failure.json")
CAP_HOURS = 720.0
QUANTILES = (0.2, 0.5, 0.8)
BASELINES = {"pump": "pump_72h", "fan": "fan_72h"}
PARAMS = dict(n_estimators=300, learning_rate=0.05, num_leaves=31, min_child_samples=200, subsample=0.8,
              subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=7, n_jobs=4)


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def time_to_next(frame, episodes, journal_end):
    starts = {ch: np.sort(g["episode_start"].values.astype("datetime64[ns]")) for ch, g in episodes.groupby("channel_id")}
    hours = np.full(len(frame), np.nan)
    observed = np.zeros(len(frame), dtype=bool)
    for ch, idx in frame.groupby("channel_id").indices.items():
        ts = frame["ts"].values[idx].astype("datetime64[ns]")
        series = starts.get(ch)
        if series is not None and len(series):
            pos = np.searchsorted(series, ts, side="right")
            found = pos < len(series)
            nxt = np.where(found, series[np.minimum(pos, len(series) - 1)], np.datetime64("NaT"))
            delta = (nxt - ts) / np.timedelta64(1, "h")
            hours[idx[found]] = delta[found]
            observed[idx[found]] = True
    censor = (np.datetime64(journal_end) - frame["ts"].values.astype("datetime64[ns]")) / np.timedelta64(1, "h")
    hours = np.where(observed, hours, censor)
    known = observed | (censor >= CAP_HOURS)
    return np.minimum(hours, CAP_HOURS), known


def concordance(time_true, risk, rng, pairs=300_000):
    i = rng.integers(0, len(time_true), pairs)
    j = rng.integers(0, len(time_true), pairs)
    mask = (time_true[i] < time_true[j]) & (time_true[i] < CAP_HOURS)
    a, b = risk[i[mask]], risk[j[mask]]
    return round(float(((a > b) + 0.5 * (a == b)).mean()), 4)


def main():
    devices = sys.argv[1:] or ["pump", "fan"]
    rng = np.random.default_rng(7)
    report = json.load(open(OUTPUT, encoding="utf-8")) if os.path.exists(OUTPUT) else {}
    for device in devices:
        ctx = DeviceContext(config.SENSOR_ALIASES[device])
        frame = ctx.features_base.reset_index(drop=True)
        journal_end = ctx.events["ts"].max()
        target, known = time_to_next(frame, ctx.episodes, journal_end)
        baseline_model, baseline_meta = artifacts.load_artifact(BASELINES[device])
        columns = [c for c in baseline_meta["feature_columns"] if c in frame.columns]
        frame = frame.assign(target=target, known=known)
        y = np.log1p(frame["target"].to_numpy())
        entry = {"cap_hours": CAP_HOURS, "periods": {}}
        final = {}
        for period, train_end, test_start, test_end in (("selection_2025", "2025-01-01", "2025-01-01", "2025-12-01"),
                                                        ("test_2026h1", "2026-01-01", "2026-01-01", "2026-06-01")):
            train = (frame["ts"] < pd.Timestamp(train_end) - pd.Timedelta(hours=CAP_HOURS)) & frame["known"]
            test = (frame["ts"] >= pd.Timestamp(test_start)) & (frame["ts"] < pd.Timestamp(test_end)) & frame["known"]
            preds = {}
            for q in QUANTILES:
                model = lgb.LGBMRegressor(objective="quantile", alpha=q, **PARAMS).fit(frame.loc[train, columns], y[train])
                preds[q] = np.expm1(model.predict(frame.loc[test, columns]))
                if period == "test_2026h1":
                    final[q] = model
            truth = frame.loc[test, "target"].to_numpy()
            lo, mid, hi = np.minimum(preds[0.2], preds[0.5]), preds[0.5], np.maximum(preds[0.8], preds[0.5])
            baseline = baseline_model.predict_proba(frame.loc[test, baseline_meta["feature_columns"]])
            event = truth < CAP_HOURS
            entry["periods"][period] = {
                "rows": int(test.sum()),
                "events_within_cap": round(float(event.mean()), 4),
                "coverage_20_80": round(float(((truth >= lo) & (truth <= hi)).mean()), 4),
                "median_abs_error_hours": round(float(np.median(np.abs(mid[event] - truth[event]))), 1),
                "median_true_hours": round(float(np.median(truth[event])), 1),
                "c_index_quantile_median": concordance(truth, -mid, rng),
                "c_index_classifier_72h": concordance(truth, baseline, rng),
            }
            log(f"{device} {period}: {entry['periods'][period]}")
        sel = entry["periods"]["selection_2025"]
        entry["decision"] = ("в прод" if 0.5 <= sel["coverage_20_80"] <= 0.7 and sel["c_index_quantile_median"] >= sel["c_index_classifier_72h"] - 0.02
                             else "в таблицу проверенных подходов")
        if entry["decision"] == "в прод":
            for q, model in final.items():
                artifacts.save_artifact(f"{device}_ttf_q{int(q * 100)}", model, columns,
                                        {"quantile": q, "cap_hours": CAP_HOURS, "target": "часов до начала следующего эпизода «Неисправен»"},
                                        {"train_years": f"{config.TRAIN_YEARS[0]}-2025"}, entry["periods"], version=time.strftime("%Y-%m-%d"))
        report[device] = entry
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)
        log(f"{device}: {entry['decision']}")
        del ctx, frame


if __name__ == "__main__":
    main()
