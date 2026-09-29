import os
import requests
import pandas as pd

from pipeline import config

CACHE_FILE = os.path.join(config.CACHE_DIR, "moscow_weather_daily.parquet")

MOSCOW_LAT = 55.7558
MOSCOW_LON = 37.6173


def fetch_weather(start_date="2019-01-01", end_date="2026-06-30", force=False):
    if os.path.exists(CACHE_FILE) and not force:
        return pd.read_parquet(CACHE_FILE)

    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        f"?latitude={MOSCOW_LAT}&longitude={MOSCOW_LON}"
        f"&start_date={start_date}&end_date={end_date}"
        "&daily=temperature_2m_mean,temperature_2m_min,precipitation_sum,relative_humidity_2m_mean,surface_pressure_mean"
        "&timezone=Europe%2FMoscow"
    )
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    daily = data["daily"]
    df = pd.DataFrame({
        "day": pd.to_datetime(daily["time"]),
        "temp_mean": daily["temperature_2m_mean"],
        "temp_min": daily["temperature_2m_min"],
        "precipitation": daily["precipitation_sum"],
        "humidity_mean": daily["relative_humidity_2m_mean"],
        "pressure_mean": daily["surface_pressure_mean"],
    })
    df.to_parquet(CACHE_FILE, index=False)
    return df


def attach_weather(candidates_df, weather_df):
    c = candidates_df.copy()
    c["day"] = c["ts"].dt.floor("D")
    merged = c.merge(weather_df, on="day", how="left")
    return merged.drop(columns=["day"])


def fetch_forecast(days=7, timeout=20):
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={MOSCOW_LAT}&longitude={MOSCOW_LON}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,snowfall_sum,precipitation_probability_max"
        f"&forecast_days={days}&timezone=Europe%2FMoscow"
    )
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    daily = resp.json()["daily"]
    rows = []
    for index, day in enumerate(daily["time"]):
        low, high = daily["temperature_2m_min"][index], daily["temperature_2m_max"][index]
        rows.append({
            "day": day,
            "temp_min": low,
            "temp_max": high,
            "precipitation_mm": daily["precipitation_sum"][index],
            "snowfall_cm": daily["snowfall_sum"][index],
            "precipitation_probability": daily["precipitation_probability_max"][index],
            "thaw": low is not None and high is not None and low < 0 < high,
        })
    return rows
