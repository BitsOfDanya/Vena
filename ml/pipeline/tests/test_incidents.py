import numpy as np
import pandas as pd

from pipeline import incidents, states


def _ts(*values):
    return pd.to_datetime(list(values))


def test_onsets_skip_repeats_within_gap():
    events = pd.DataFrame({
        "channel_id": ["1", "1", "1", "2"],
        "ts": _ts("2026-01-01 10:00", "2026-01-01 10:10", "2026-01-01 11:00", "2026-01-01 10:05"),
        "raw_value": ["Обнаружен дым"] * 4,
    })
    out = incidents.onsets(events, "Обнаружен дым", 30)
    assert list(zip(out["channel_id"], out["ts"].dt.strftime("%H:%M"))) == [("1", "10:00"), ("1", "11:00"), ("2", "10:05")]


def test_bursts_group_by_object_and_window():
    onset = pd.DataFrame({
        "channel_id": ["1", "2", "3", "1"],
        "ts": _ts("2026-01-01 10:00", "2026-01-01 10:10", "2026-01-01 10:12", "2026-01-01 12:00"),
    })
    out = incidents.bursts(onset, {"1": "A", "2": "A", "3": "B"}, 15)
    assert sorted(zip(out["object"], out["channels"])) == [("A", 1), ("A", 2), ("B", 1)]


def test_maintenance_series_needs_weekday_work_hours():
    frame = pd.DataFrame({"t0": _ts("2026-01-05 10:00", "2026-01-04 10:00", "2026-01-05 20:00"), "channels": [5, 5, 5]})
    assert incidents._maintenance(frame).tolist() == [True, False, False]


def test_technical_fault_respects_alarm_flag_and_limits():
    values = ["-127", "21,5", "128", "-127", "Норма"]
    flags = ["f", "f", "f", "t", "f"]
    out = states.technical_fault(values, flags, states.TEMPERATURE_LIMITS)
    assert out.tolist() == [True, False, True, False, False]
    assert np.array_equal(states.technical_fault(["255"], ["f"]), np.array([True]))


def test_flood_rule_on_given_events_needs_two_pumps_or_long_flooding():
    events = pd.DataFrame({
        "channel_id": ["1", "1", "2", "2", "3", "3"],
        "ts": _ts("2026-01-01 10:00", "2026-01-01 10:05", "2026-01-01 10:20", "2026-01-01 10:25",
                  "2026-01-02 09:00", "2026-01-02 09:45"),
        "raw_value": ["Затоплен", "Норма", "Затоплен", "Норма", "Затоплен", "Норма"],
    })
    out = incidents.flood_incidents({"1": "A", "2": "A", "3": "B"}, events)
    assert sorted(zip(out["object"], out["channels"])) == [("A", 2), ("B", 1)]


def test_power_rule_on_given_events_needs_three_feeders():
    events = pd.DataFrame({
        "channel_id": ["1", "2", "3", "4"],
        "ts": _ts("2026-01-01 10:00", "2026-01-01 10:01", "2026-01-01 10:02", "2026-01-01 10:00"),
        "raw_value": ["Обесточен"] * 4,
    })
    out = incidents.power_incidents({"1": "A", "2": "A", "3": "A", "4": "B"}, events)
    assert out["object"].tolist() == ["A"] and out["channels"].tolist() == [3]
