"""Flooding forecast: onset of the pump chamber state "Затоплен".

The ТЗ flooding scenario compares pump activity with the weather forecast. Pump
duty-cycle features describe how often the pumps switch on; weather features use
only days before the candidate, and the forecast block adds the precipitation of
the candidate day and the next day. In backtests the forecast block is filled
with observed precipitation, which is an upper bound of a real forecast.
"""

import numpy as np
import pandas as pd

from pipeline import episodes as episodes_mod
from pipeline import features as features_mod
from pipeline.targets import discovery, state_target

FLOOD_STATE = "Затоплен"
PAST_WEATHER = ["precip_prev_1d", "precip_prev_3d", "precip_prev_7d", "temp_prev_1d", "thaw_prev_3d"]
FORECAST_WEATHER = ["precip_forecast_0d", "precip_forecast_1d"]


def weather_features(ts, weather):
    """Weather known at `ts` plus the precipitation forecast for today and tomorrow."""
    daily = weather.set_index("day").sort_index()
    precip = daily["precipitation"].fillna(0.0)
    temp = daily["temp_mean"]
    # Snow melt: days with mean temperature above zero after a frost.
    thaw = ((temp > 0) & (daily["temp_min"] < 0)).astype(float)
    table = pd.DataFrame({
        "precip_prev_1d": precip.shift(1),
        "precip_prev_3d": precip.shift(1).rolling(3, min_periods=1).sum(),
        "precip_prev_7d": precip.shift(1).rolling(7, min_periods=1).sum(),
        "temp_prev_1d": temp.shift(1),
        "thaw_prev_3d": thaw.shift(1).rolling(3, min_periods=1).sum(),
        "precip_forecast_0d": precip,
        "precip_forecast_1d": precip.shift(-1),
    })
    days = pd.DatetimeIndex(pd.to_datetime(ts)).floor("D")
    return table.reindex(days).reset_index(drop=True)


def build_frame(events, weather, horizon_hours=24):
    events = events.sort_values(["channel_id", "ts"], kind="stable").reset_index(drop=True)
    episodes = discovery.state_episodes(events, FLOOD_STATE)
    candidates = state_target.event_candidates(events, FLOOD_STATE)
    rates = state_target.global_rates(events, FLOOD_STATE, 2023)
    frame = features_mod.compute_features(
        candidates, events, episodes, numeric_mode=False, duty_cycle_mode=True, global_rates=rates,
    )
    frame = episodes_mod.assign_targets(frame, episodes, horizon_hours)
    extra = weather_features(frame["ts"], weather)
    frame = pd.concat([frame.reset_index(drop=True), extra], axis=1)
    return frame, episodes, rates


def attach_to_row(row, ts, weather):
    extra = weather_features([ts], weather)
    for column in extra.columns:
        row[column] = np.asarray(extra[column].values, dtype=float)
    return row
