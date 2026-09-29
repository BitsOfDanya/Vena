import json
import os
import time

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from pipeline import config, extract, weather as weather_mod
from pipeline.targets import discovery
from run_seasonality import SCENARIOS

LEADS = range(1, 15)
START = pd.Timestamp("2019-04-01")
SELECTION_YEAR = 2025
RECENT_YEAR = 2026
HOLIDAYS = {(1, day) for day in range(1, 9)} | {(2, 23), (3, 8), (5, 1), (5, 9), (6, 12), (11, 4)}
OUTPUT = os.path.join(config.ROOT, "results", "workload_forecast.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def daily_counts():
    counts = {}
    for scenario, (sensor, state) in SCENARIOS.items():
        starts = discovery.state_episodes(extract.extract_events(sensor), state)["episode_start"]
        counts[scenario] = starts.dt.floor("D").value_counts()
    frame = pd.DataFrame(counts).fillna(0).sort_index()
    return frame.loc[frame.index >= START].asfreq("D", fill_value=0)


def is_holiday(days):
    return np.array([(day.month, day.day) in HOLIDAYS for day in days], dtype=float)


def rows(series, weather, origins):
    values = series.to_numpy(dtype=float)
    index = {day: position for position, day in enumerate(series.index)}
    cumulative = np.concatenate([[0.0], np.cumsum(values)])

    def mean(end, days):
        start = max(end - days, 0)
        return (cumulative[end] - cumulative[start]) / max(end - start, 1)

    records = []
    for origin in origins:
        end = index[origin]
        level7, level28, level91 = mean(end, 7), mean(end, 28), mean(end, 91)
        past = weather.loc[:origin - pd.Timedelta(days=1)].tail(7)
        for lead in LEADS:
            day = origin + pd.Timedelta(days=lead - 1)
            same_weekday = [day - pd.Timedelta(days=7 * week) for week in range(1, 7)]
            known = [values[index[d]] for d in same_weekday if d < origin and d in index][:4]
            weekday_mean = float(np.mean(known)) if known else level28
            year_ago = index.get(day - pd.Timedelta(days=364))
            records.append({
                "origin": origin, "day": day, "lead": lead,
                "level7": level7, "level28": level28, "level91": level91, "weekday_mean": weekday_mean,
                "year_ago": mean(year_ago + 4, 7) if year_ago is not None and year_ago >= 3 else np.nan,
                "weekday": day.weekday(), "month": day.month,
                "doy_sin": np.sin(2 * np.pi * day.dayofyear / 365.25), "doy_cos": np.cos(2 * np.pi * day.dayofyear / 365.25),
                "holiday": float((day.month, day.day) in HOLIDAYS),
                "precip_3d": float(past["precipitation"].tail(3).sum()) if len(past) else np.nan,
                "thaw_7d": float(((past["temp_mean"] > 0) & (past["temp_min"] < 0)).sum()) if len(past) else np.nan,
                "target": values[index[day]] if day in index else np.nan,
            })
    return pd.DataFrame(records)


VARIANTS = {
    "calendar+level": ["lead", "level7", "level28", "level91", "weekday_mean", "year_ago", "weekday", "month",
                       "doy_sin", "doy_cos", "holiday"],
}
VARIANTS["calendar+level+weather"] = VARIANTS["calendar+level"] + ["precip_3d", "thaw_7d"]


def fit(frame, columns):
    model = HistGradientBoostingRegressor(loss="poisson", max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                          min_samples_leaf=40, random_state=42)
    return model.fit(frame[columns], frame["target"])


METHODS = [*VARIANTS, "last_28_days"]


def predict(method, models, frame):
    if method == "last_28_days":
        return frame["level28"].to_numpy()
    return models[method].predict(frame[VARIANTS[method]])


def weekly(frame, forecast):
    scored = frame.assign(forecast=forecast)
    return scored.loc[scored["lead"] <= 7].groupby("origin")[["target", "forecast"]].sum()


def wape(actual, forecast):
    return round(float(np.abs(forecast - actual).sum() / max(actual.sum(), 1e-9)), 4)


def errors(frame, forecast):
    week = weekly(frame, forecast)
    return {"day": wape(frame["target"].to_numpy(), np.asarray(forecast)), "week": wape(week["target"], week["forecast"])}


def study(scenario, series, weather):
    days = series.index
    last = days.max()
    origins = days[(days >= START + pd.Timedelta(days=120)) & (days <= last - pd.Timedelta(days=max(LEADS) - 1))]
    frame = rows(series, weather, origins).dropna(subset=["target"])
    target_year = frame["day"].dt.year
    select = frame.loc[(target_year == SELECTION_YEAR) & (frame["origin"].dt.year == SELECTION_YEAR)]
    recent = frame.loc[(target_year == RECENT_YEAR) & (frame["origin"].dt.year == RECENT_YEAR)]

    before_selection = frame.loc[frame["day"] < pd.Timestamp(f"{SELECTION_YEAR}-01-01")]
    staging = {variant: fit(before_selection, columns) for variant, columns in VARIANTS.items()}
    selection = {method: errors(select, predict(method, staging, select)) for method in METHODS}
    best = min(selection, key=lambda name: selection[name]["week"])
    week = weekly(select, predict(best, staging, select))
    low, high = np.quantile(week["target"] / np.maximum(week["forecast"], 1e-6), [0.1, 0.9])

    before_recent = frame.loc[frame["day"] < pd.Timestamp(f"{RECENT_YEAR}-01-01")]
    fitted = {variant: fit(before_recent, columns) for variant, columns in VARIANTS.items()}
    next_day = recent.loc[recent["lead"] == 1]
    report = {
        "selection_2025": selection,
        "method": best,
        "recent": {
            "period": f"{RECENT_YEAR}H1",
            **{method: errors(recent, predict(method, fitted, recent)) for method in METHODS},
            "same_weekday_4_weeks": errors(recent, recent["weekday_mean"].to_numpy()),
            "mean_per_day": round(float(next_day["target"].mean()), 2),
        },
        "week_interval_80": [round(float(low), 3), round(float(high), 3)],
        "history": {
            "last_30_days": int(series.iloc[-30:].sum()),
            "last_365_days": int(series.iloc[-365:].sum()),
        },
        "backtest": [
            {"day": day.date().isoformat(), "actual": int(actual), "forecast": round(float(value), 1)}
            for day, actual, value in zip(next_day["day"], next_day["target"], predict(best, fitted, next_day), strict=True)
        ],
    }
    final = {variant: fit(frame, columns) for variant, columns in VARIANTS.items()}
    ahead = rows(series.reindex(pd.date_range(days.min(), last + pd.Timedelta(days=max(LEADS)), freq="D")),
                 weather, [last + pd.Timedelta(days=1)])
    assert series.reindex(ahead["day"]).isna().all(), "forecast days must lie after the journal"
    forecast = predict(best, final, ahead)
    report["forecast"] = [{"day": day.date().isoformat(), "expected": round(float(value), 1)}
                          for day, value in zip(ahead["day"], forecast, strict=True)]
    total = float(forecast[:7].sum())
    report["next_7_days"] = {"expected": round(total, 1), "low": round(total * low, 1), "high": round(total * high, 1)}
    log(f"{scenario}: {best}, 2026H1 week WAPE {report['recent'][best]['week']} "
        f"vs {report['recent']['last_28_days']['week']} (28 days)")
    return report


def main() -> None:
    counts = daily_counts()
    weather = weather_mod.fetch_weather().set_index("day").sort_index()
    weather.index = pd.to_datetime(weather.index)
    report = {"journal_end": counts.index.max().date().isoformat(), "scenarios": {}}
    for scenario in counts.columns:
        report["scenarios"][scenario] = study(scenario, counts[scenario], weather)
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(f"report -> {OUTPUT}")


if __name__ == "__main__":
    main()
