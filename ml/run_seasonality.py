import json
import os
import time

import numpy as np
import pandas as pd

from pipeline import config, extract, weather as weather_mod
from pipeline.targets import discovery

OUTPUT = os.path.join(config.ROOT, "results", "seasonality.json")
SCENARIOS = {
    "flooding": ("Состояние насоса", "Затоплен"),
    "pump_fault": ("Состояние насоса", config.FAULT_LITERAL),
    "ventilation_fault": ("Состояние вентилятора", config.FAULT_LITERAL),
    "smoke_sensor_fault": ("Датчик дыма", config.FAULT_LITERAL),
    "smoke_detected": ("Датчик дыма", "Обнаружен дым"),
    "power_loss": ("Состояние фазы", "Обесточен"),
}
SEASONS = {12: "winter", 1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "spring",
           6: "summer", 7: "summer", 8: "summer", 9: "autumn", 10: "autumn", 11: "autumn"}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> None:
    weather = weather_mod.fetch_weather().set_index("day").sort_index()
    report = {"monthly_onsets_per_100_channels": {}, "seasonal_share": {}}
    daily_flood = None
    for scenario, (sensor, state) in SCENARIOS.items():
        events = extract.extract_events(sensor)
        episodes = discovery.state_episodes(events, state)
        channels = max(events["channel_id"].nunique(), 1)
        starts = episodes["episode_start"]
        full = starts[starts.dt.year < 2026]
        years = max(full.dt.year.nunique(), 1)
        monthly = full.dt.month.value_counts().sort_index() / years / channels * 100
        report["monthly_onsets_per_100_channels"][scenario] = {int(m): round(float(v), 2) for m, v in monthly.items()}
        season = full.dt.month.map(SEASONS).value_counts(normalize=True)
        report["seasonal_share"][scenario] = {k: round(float(v), 4) for k, v in season.items()}
        if scenario == "flooding":
            daily_flood = starts.dt.floor("D").value_counts().sort_index()
        log(f"{scenario}: {len(episodes)} episodes on {channels} channels")

    days = pd.date_range(weather.index.min(), min(weather.index.max(), daily_flood.index.max()), freq="D")
    flood = daily_flood.reindex(days, fill_value=0).astype(float)
    precip = weather["precipitation"].reindex(days).fillna(0.0)
    thaw = ((weather["temp_mean"] > 0) & (weather["temp_min"] < 0)).astype(float).reindex(days).fillna(0.0)
    link = {}
    for lag in (0, 1, 2):
        link[f"precipitation_lag{lag}d"] = round(float(flood.corr(precip.shift(lag))), 4)
        link[f"thaw_lag{lag}d"] = round(float(flood.corr(thaw.shift(lag))), 4)
    heavy = precip >= np.quantile(precip[precip > 0], 0.9)
    link["flood_onsets_per_day_heavy_rain"] = round(float(flood[heavy].mean()), 3)
    link["flood_onsets_per_day_other"] = round(float(flood[~heavy].mean()), 3)
    report["flooding_vs_weather"] = link

    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    log(json.dumps(report["flooding_vs_weather"], indent=1))


if __name__ == "__main__":
    main()
