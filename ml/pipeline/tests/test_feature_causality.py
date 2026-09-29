import numpy as np

from pipeline.features import _channel_features


def test_unobserved_future_failure_does_not_change_current_features():
    events = np.array(["2024-01-01T08:00:00", "2024-01-02T08:00:00"], dtype="datetime64[s]")
    candidates = np.array(["2024-01-02T09:00:00"], dtype="datetime64[s]")
    alarms = np.array([0, 1])
    values = np.array(["Включен", "Выключен"])
    rates = {"event": 1.0, "alarm": 0.1, "failure": 0.05}
    without_future = _channel_features(
        candidates, events, alarms, values, np.array([], dtype="datetime64[s]"),
        global_rates=rates,
    )
    with_future = _channel_features(
        candidates, events, alarms, values,
        np.array(["2024-02-01T00:00:00"], dtype="datetime64[s]"),
        global_rates=rates,
    )
    assert without_future.keys() == with_future.keys()
    for name in without_future:
        np.testing.assert_allclose(without_future[name], with_future[name], err_msg=name)
