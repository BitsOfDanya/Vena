import pandas as pd

from pipeline.prospective import ProspectiveMonitor


def _rows(day, ranking, probability=0.5, short=None):
    rows = []
    for place, obj in enumerate(ranking, start=1):
        row = {"model_id": "object_flood_24h", "object_id": obj, "day": day, "probability": probability, "rank": place}
        if short is not None:
            row["probability_6h"], row["rank_6h"] = 0.1, short.index(obj) + 1
        rows.append(row)
    return rows


def test_daily_lists_are_scored_against_registry_incidents():
    monitor = ProspectiveMonitor("2026-06-03")
    monitor.record_objects(_rows("2026-06-02", ["A", "B", "C", "D"]), "2026-06-02 23:00")
    monitor.record_objects(_rows("2026-06-03", ["A", "B", "C", "D"]), "2026-06-03 01:00")
    monitor.record_objects(_rows("2026-06-04", ["D", "C", "B", "A"]), "2026-06-04 01:00")
    flood = pd.DataFrame({"object": ["B", "A", "C"], "t0": pd.to_datetime(["2026-06-03 10:00", "2026-06-04 12:00", "2026-06-06 09:00"])})
    report = monitor.evaluate_objects({"flood": flood}, "2026-06-05 00:00")["object_flood_24h"]
    assert report["lists"] == 2 and report["forecasts"] == 8
    assert report["event_rate"] == 0.25
    assert report["incidents"] == 2 and report["incidents_top3"] == 1
    assert report["top3_precision"] == round(1 / 6, 4)


def test_hourly_list_needs_six_hours_of_lead():
    monitor = ProspectiveMonitor("2026-06-03")
    order = ["B", "A", "C", "D"]
    monitor.record_objects(_rows("2026-06-03", ["A", "B", "C", "D"], short=order), "2026-06-03 02:00")
    monitor.record_objects(_rows("2026-06-03", ["A", "B", "C", "D"], short=["D", "C", "A", "B"]), "2026-06-03 05:30")
    flood = pd.DataFrame({"object": ["B"], "t0": pd.to_datetime(["2026-06-03 08:00"])})
    report = monitor.evaluate_objects({"flood": flood}, "2026-06-03 12:00")["object_flood_6h"]
    assert report["lists"] == 2
    assert report["incidents"] == 1 and report["incidents_top3"] == 1
    assert report["event_rate"] == round(2 / 8, 4)


def test_incident_without_a_list_in_lead_window_is_not_counted():
    monitor = ProspectiveMonitor("2026-06-03")
    monitor.record_objects(_rows("2026-06-03", ["A", "B", "C", "D"], short=["B", "A", "C", "D"]), "2026-06-03 00:30")
    flood = pd.DataFrame({"object": ["B", "A", "C"], "t0": pd.to_datetime(["2026-06-03 05:00", "2026-06-03 06:40", "2026-06-03 00:20"])})
    report = monitor.evaluate_objects({"flood": flood}, "2026-06-03 12:00")["object_flood_6h"]
    assert report["incidents_total"] == 1 and report["incidents"] == 1 and report["incidents_top3"] == 1


def test_list_computed_after_onset_does_not_count_as_lead():
    monitor = ProspectiveMonitor("2026-06-03")
    monitor.record_objects(_rows("2026-06-03", ["A", "B", "C", "D"], short=["B", "A", "C", "D"]), "2026-06-03 20:59")
    flood = pd.DataFrame({"object": ["B"], "t0": pd.to_datetime(["2026-06-03 20:30"])})
    report = monitor.evaluate_objects({"flood": flood}, "2026-06-04 06:00")["object_flood_6h"]
    assert report["incidents_total"] == 0 and report["incidents"] == 0
