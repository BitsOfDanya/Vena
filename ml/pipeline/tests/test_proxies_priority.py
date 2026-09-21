import numpy as np
import pandas as pd
import pytest

from pipeline.targets import priority, proxies


def test_fire_proxy_is_monotone_and_bounded():
    low = pd.DataFrame({"alarm_ch_prev_1h": [0], "alarm_grp_prev_1h": [0], "alarm_grp_prev_24h": [0] })
    high = pd.DataFrame({"alarm_ch_prev_1h": [10], "alarm_grp_prev_1h": [30], "alarm_grp_prev_24h": [100] })
    a, b = proxies.fire_risk_proxy(low)[0], proxies.fire_risk_proxy(high)[0]
    assert 0.0 <= a < b <= 1.0


def test_fire_proxy_uses_only_past_alarm_columns():
    x = pd.DataFrame({"alarm_ch_prev_1h": [1], "alarm_grp_prev_1h": [1], "alarm_grp_prev_24h": [1]})
    with_future = x.assign(dwell_minutes=[9999.0], c30_corroborated=[1])
    assert proxies.fire_risk_proxy(x)[0] == proxies.fire_risk_proxy(with_future)[0]


def test_hydraulic_anomaly_increases_with_load_above_channel_baseline():
    base = {"events_6h": 6.0, "channel_event_prior": 24.0, "burst_count_24h": 0.0, "events_1h": 1.0}
    busy = {"events_6h": 120.0, "channel_event_prior": 24.0, "burst_count_24h": 40.0, "events_1h": 40.0}
    a = proxies.hydraulic_load_anomaly(pd.DataFrame([base]))[0]
    b = proxies.hydraulic_load_anomaly(pd.DataFrame([busy]))[0]
    assert a < b


def test_priority_combines_available_signals_and_reports_reason():
    signals = {"equipment_failure": [0.1, 0.9, 0.5], "power_failure": [0.2, 0.1, np.nan]}
    out = priority.maintenance_priority(signals)
    assert out["signals_available"].tolist() == [2, 2, 1]
    assert out.loc[1, "top_reason"] == "equipment_failure"
    assert out["priority"].iloc[1] > out["priority"].iloc[0]


def test_priority_is_invariant_to_monotone_rescaling_of_a_signal():
    s = np.array([0.1, 0.5, 0.2, 0.9])
    a = priority.maintenance_priority({"equipment_failure": s, "alarm_confidence": s[::-1]})
    b = priority.maintenance_priority({"equipment_failure": s * 100 + 3, "alarm_confidence": s[::-1]})
    assert np.allclose(a["priority"], b["priority"])


def test_priority_rejects_unknown_signals_only():
    with pytest.raises(ValueError):
        priority.maintenance_priority({"foo": [1, 2]})
