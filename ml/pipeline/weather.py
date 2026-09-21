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
