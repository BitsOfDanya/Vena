"""Two-pump chamber mass balance, independent of all ML scores and thresholds."""

import numpy as np
import pandas as pd

SCENARIOS = (
    "normal",
    "gradual_degradation",
    "sudden_failure",
    "power_loss",
    "high_inflow",
    "stuck_level_sensor",
    "maintenance",
    "telemetry_loss",
)
EVENT_COLUMNS = ["channel_id", "ts", "raw_value", "alarm_flag"]
TRUTH_COLUMNS = ["channel_id", "episode_start", "episode_end", "kind"]


def boolean_episodes(channel, times, flags, kind):
    flags = np.asarray(flags, dtype=bool)
    starts = np.flatnonzero(flags & ~np.r_[False, flags[:-1]])
    ends = np.flatnonzero(flags & ~np.r_[flags[1:], False])
    return [
        {
            "channel_id": channel,
            "episode_start": times[a],
            "episode_end": times[b],
            "kind": kind,
        }
        for a, b in zip(starts, ends)
    ]


def simulate(scenario, seed, days=90):
    if scenario not in SCENARIOS:
        raise ValueError(scenario)
    rng = np.random.default_rng(seed)
    station = f"{scenario}-{seed}"
    times = pd.date_range("2026-07-01", periods=days * 288 + 1, freq="5min")
    dt = 5.0  # minutes; flows in m3/min; chamber area in m2
    area = rng.uniform(16, 25)
    capacity = rng.uniform(0.24, 0.34, 2)
    inflow_mean = rng.uniform(0.075, 0.115)
    disturbance = rng.uniform(52, 62) * 1440
    event_rows, physical_rows = [], []
    level, observed_level = 0.7, 0.7
    running = np.zeros(2, dtype=bool)
    last_values = [None, None, None]
    truth_flags = {"pump1": [], "pump2": [], "phase": [], "flood": []}
    max_balance_error = 0.0
    for i, timestamp in enumerate(times):
        minute = i * dt
        age = minute - disturbance
        during = 0 <= age < 4 * 1440
        inflow = inflow_mean * (1 + 0.2 * np.sin(2 * np.pi * minute / 1440))
        inflow *= max(0.2, 1 + rng.normal(0, 0.04))
        efficiency = np.ones(2)
        faults = np.zeros(2, dtype=bool)
        powered = True
        if scenario == "gradual_degradation" and 0 <= age < 9 * 1440:
            efficiency[:] = max(0.15, 1 - 0.85 * age / (5 * 1440))
            faults[:] = efficiency <= 0.25
        elif scenario == "sudden_failure" and during:
            faults[0], efficiency[0] = True, 0.0
        elif scenario == "power_loss" and 0 <= age < 36 * 60:
            powered = False
        elif scenario == "high_inflow" and during:
            inflow *= 8
        if not (scenario == "stuck_level_sensor" and during):
            observed_level = level
        else:
            observed_level = 0.55
        for pump, on_level in enumerate((1.1, 1.4)):
            if observed_level >= on_level:
                running[pump] = True
            elif observed_level <= 0.6:
                running[pump] = False
        discharge = float(np.sum(capacity * efficiency * running)) if powered else 0.0
        # Limit discharge to available water. Overflow at 2.2 m is accounted for.
        volume = area * level
        removed = min(discharge * dt, volume + inflow * dt)
        remaining = volume + inflow * dt - removed
        overflow = max(remaining - area * 2.2, 0.0)
        level = (remaining - overflow) / area
        error = abs(area * level - volume - inflow * dt + removed + overflow)
        max_balance_error = max(max_balance_error, error)
        flooded = level >= 1.8
        truth_flags["pump1"].append(bool(faults[0]))
        truth_flags["pump2"].append(bool(faults[1]))
        truth_flags["phase"].append(not powered)
        truth_flags["flood"].append(flooded)
        # Log level seen before this step, making observations causal.
        visible_flood = observed_level >= 1.8
        values = []
        for pump in range(2):
            value = (
                "Обесточен"
                if not powered
                else "Неисправен"
                if faults[pump]
                else "Затоплен"
                if visible_flood
                else "Включен"
                if running[pump]
                else "Выключен"
            )
            if scenario == "maintenance" and 0 <= age < 2 * 60:
                value = "Неисправен" if i % 2 else "Выключен"
            values.append(value)
        values.append("Норма" if powered else "Обесточен")
        telemetry_missing = scenario == "telemetry_loss" and during
        for j, value in enumerate(values):
            # Transitions plus a daily heartbeat, not repeated fake fault labels.
            if not telemetry_missing and (value != last_values[j] or i % 288 == 0):
                suffix = f"pump{j + 1}" if j < 2 else "phase"
                event_rows.append(
                    (
                        f"{station}/{suffix}",
                        timestamp,
                        value,
                        int(value in ("Неисправен", "Обесточен", "Затоплен")),
                    )
                )
                last_values[j] = value
        if i % 12 == 0:
            physical_rows.append(
                (
                    timestamp,
                    level,
                    observed_level,
                    inflow,
                    removed / dt,
                    overflow,
                    powered,
                )
            )
    truth = []
    for suffix in ("pump1", "pump2"):
        truth.extend(
            boolean_episodes(f"{station}/{suffix}", times, truth_flags[suffix], "pump")
        )
        truth.extend(
            boolean_episodes(
                f"{station}/{suffix}", times, truth_flags["flood"], "flood"
            )
        )
    truth.extend(
        boolean_episodes(f"{station}/phase", times, truth_flags["phase"], "phase")
    )
    return {
        "station": station,
        "scenario": scenario,
        "seed": seed,
        "events": pd.DataFrame(event_rows, columns=EVENT_COLUMNS),
        "truth": pd.DataFrame(truth, columns=TRUTH_COLUMNS),
        "physics": pd.DataFrame(
            physical_rows,
            columns=[
                "ts",
                "level_m",
                "observed_level_m",
                "inflow_m3_min",
                "discharge_m3_min",
                "overflow_m3",
                "powered",
            ],
        ),
        "parameters": {
            "area_m2": area,
            "pump_capacity_m3_min": capacity.tolist(),
            "mean_inflow_m3_min": inflow_mean,
            "disturbance_day": disturbance / 1440,
            "step_minutes": dt,
            "max_mass_balance_error_m3": max_balance_error,
        },
        "start": times[30 * 288],
        "end": times[-1],
    }
