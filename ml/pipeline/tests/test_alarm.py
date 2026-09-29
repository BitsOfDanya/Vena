import numpy as np
import pandas as pd

from pipeline.targets import alarm

T0 = pd.Timestamp("2024-01-01")


def _alarms(rows):
    return pd.DataFrame([(c, T0 + pd.Timedelta(minutes=m), d, g) for c, m, d, g in rows],
                        columns=["channel_id", "ts", "dwell_minutes", "tag_group"])


def test_repeat_window_is_strictly_after_and_inclusive_of_upper_bound():
    a = _alarms([("a", 0, 0.0, "g"), ("a", 30, 0.0, "g"), ("a", 90, 0.0, "g")])
    lab = alarm.corroboration_labels(a, 30)
    assert lab["repeat"].tolist() == [True, False, False]
    assert alarm.corroboration_labels(a, 15)["repeat"].tolist() == [False, False, False]


def test_neighbor_excludes_own_channel_and_other_groups():
    a = _alarms([("a", 0, 0.0, "g1"), ("b", 10, 0.0, "g1"), ("c", 10, 0.0, "g2")])
    lab = alarm.corroboration_labels(a, 30)
    assert lab["neighbor"].tolist() == [True, False, False]
    assert lab["repeat"].tolist() == [False, False, False]


def test_sustained_uses_dwell_and_corroborated_is_union():
    a = _alarms([("a", 0, 45.0, "g1"), ("b", 500, np.inf, "g2"), ("c", 1000, 5.0, "g3")])
    lab = alarm.corroboration_labels(a, 30)
    assert lab["sustained"].tolist() == [True, True, False]
    assert lab["corroborated"].tolist() == [True, True, False]


def test_labels_are_invariant_to_events_after_the_window():
    rows = [("a", 0, 0.0, "g"), ("a", 20, 0.0, "g"), ("b", 500, 0.0, "g"), ("a", 900, 0.0, "g")]
    full = alarm.corroboration_labels(_alarms(rows), 30)
    truncated = alarm.corroboration_labels(_alarms(rows[:2]), 30)
    assert full["corroborated"].tolist()[:2] == truncated["corroborated"].tolist()


def test_group_history_features_only_use_past_alarms():
    rows = [("a", 0, 0.0, "g"), ("b", 5, 0.0, "g"), ("a", 20, 0.0, "g"), ("a", 100, 0.0, "g")]
    base = alarm.group_history_features(_alarms(rows))
    changed = alarm.group_history_features(_alarms(rows + [("a", 200, 0.0, "g"), ("b", 210, 0.0, "g")]))
    assert base.equals(changed.iloc[:4])
    assert base.loc[2, "alarm_ch_prev_1h"] == 1
    assert base.loc[2, "alarm_grp_prev_1h"] == 1


def test_detection_alarms_pick_only_flagged_detection_events():
    ev = pd.DataFrame({
        "channel_id": ["a"] * 4, "ts": [T0 + pd.Timedelta(minutes=m) for m in (0, 10, 20, 90)],
        "alarm_flag": [0, 1, 1, 1], "raw_value": ["Норма", "Обнаружен дым", "Обнаружен дым", "Неисправен"],
    })
    out = alarm.detection_alarms(ev, "Датчик дыма", {"a": "1-2.3.4.5."})
    assert len(out) == 2
    assert out.loc[0, "dwell_minutes"] == 80.0
    assert out.loc[1, "dwell_minutes"] == 70.0


def test_maintenance_series_needs_many_detectors_of_one_object_in_working_hours():
    def alarms(start, channels, step_minutes=1):
        times = pd.date_range(start, periods=len(channels), freq=f"{step_minutes}min")
        return pd.DataFrame({"channel_id": channels, "ts": times, "sensor_type": "Датчик дыма"})

    objects = {str(c): "7" for c in range(1, 20)}
    working = alarms("2025-03-04 10:00", ["1", "2", "3", "4", "5"])
    night = alarms("2025-03-04 23:00", ["1", "2", "3", "4", "5"])
    repeated = alarms("2025-03-04 11:00", ["1", "1", "1", "2", "2"])
    slow = alarms("2025-03-04 12:00", ["1", "2", "3", "4", "5"], step_minutes=5)
    frame = pd.concat([working, night, repeated, slow], ignore_index=True)
    flag = alarm.maintenance_series(frame, objects)
    assert flag[:5].all()
    assert not flag[5:].any()
