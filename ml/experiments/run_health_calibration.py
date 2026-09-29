import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

from pipeline import calibration
from run_health_index import daily_cuts

OUTPUT = os.path.join(os.path.dirname(__file__), "health_calibration.json")
EPS = 1e-6


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def logit(raw):
    clipped = np.clip(raw, EPS, 1 - EPS)
    return np.log(clipped / (1 - clipped))


def isotonic(raw, event):
    fitted = calibration.fit_isotonic(raw, event)
    return lambda values: np.clip(calibration.apply_isotonic(fitted, values), 0, 1)


def platt(raw, event):
    model = LogisticRegression(C=1e6).fit(logit(raw)[:, None], event)
    return lambda values: model.predict_proba(logit(values)[:, None])[:, 1]


def platt_quadratic(raw, event):
    features = lambda values: np.column_stack([logit(values), logit(values) ** 2])
    model = LogisticRegression(C=1e6, max_iter=1000).fit(features(raw), event)
    grid = np.linspace(logit(np.array([EPS]))[0], logit(np.array([1 - EPS]))[0], 2000)
    curve = np.maximum.accumulate(model.predict_proba(np.column_stack([grid, grid**2]))[:, 1])
    return lambda values: np.interp(logit(values), grid, curve)


def smooth_isotonic(raw, event):
    points = calibration.fit_smooth_isotonic(raw, event)
    return lambda values: calibration.apply_points(points, values)


METHODS = {"isotonic": isotonic, "platt_logit": platt, "platt_logit_quadratic": platt_quadratic, "smooth_isotonic": smooth_isotonic}


def quality(event, risk, day):
    index = np.round(100 * (1 - risk)).astype(int)
    top = pd.DataFrame({"day": day, "index": index, "risk": risk}).sort_values("risk", ascending=False).groupby("day").head(20)
    distinct = top.groupby("day")["index"].nunique().mean()
    return {
        "ece": round(float(calibration.expected_calibration_error(event, risk)[0]), 4),
        "brier": round(float(brier_score_loss(event, risk)), 4),
        "roc_auc": round(float(roc_auc_score(event, risk)), 4),
        "avg_precision": round(float(average_precision_score(event, risk)), 4),
        "predicted": round(float(risk.mean()), 4),
        "observed": round(float(event.mean()), 4),
        "distinct_index_in_top20_per_day": round(float(distinct), 2),
        "modal_index_share": round(float(pd.Series(index).value_counts(normalize=True).iloc[0]), 4),
    }


def by_raw(daily, edges):
    cut = pd.cut(daily["raw"], edges, include_lowest=True)
    table = daily.groupby(cut, observed=True)["event"].agg(["size", "mean"])
    return [{"raw": str(key), "location_days": int(row["size"]), "event_rate": round(float(row["mean"]), 4)} for key, row in table.iterrows()]


def main() -> None:
    train, test = daily_cuts(2025, reuse=True), daily_cuts(2026, reuse=True)
    log(f"2025: {len(train)} location-days, 2026: {len(test)}")
    edges = [0, 0.05, 0.1, 0.2, 0.32, 0.5, 0.7, 0.9, 0.95, 0.98, 0.99, 0.995, 1.0]
    report = {"train": "2025 daily location cuts, models out of sample", "test": "2026H1 daily cuts, production models",
              "event_rate_by_raw_2025": by_raw(train, edges), "event_rate_by_raw_2026": by_raw(test, edges), "methods": {}}
    x, y = train["raw"].to_numpy(), train["event"].to_numpy().astype(int)
    tx, ty = test["raw"].to_numpy(), test["event"].to_numpy().astype(int)
    report["raw"] = {"2025": quality(y, x, train["day"]), "2026H1": quality(ty, tx, test["day"])}
    for name, method in METHODS.items():
        apply = method(x, y)
        report["methods"][name] = {"2025": quality(y, apply(x), train["day"]), "2026H1": quality(ty, apply(tx), test["day"])}
        log(f"{name}: {report['methods'][name]['2026H1']}")
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
