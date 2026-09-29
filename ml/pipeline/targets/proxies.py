import numpy as np

FIRE_PROXY_WEIGHTS = {"channel_repeat_1h": 0.4, "group_neighbors_1h": 0.4, "group_burst_24h": 0.2}
HYDRAULIC_WEIGHTS = {"load_z": 0.5, "rapid_switching": 0.3, "burst_share": 0.2}


def _squash(x, scale):
    return 1.0 - np.exp(-np.clip(np.asarray(x, dtype=float), 0.0, None) / scale)


def fire_risk_proxy(alarm_features, weights=None):
    w = weights or FIRE_PROXY_WEIGHTS
    parts = {
        "channel_repeat_1h": _squash(alarm_features["alarm_ch_prev_1h"], 3.0),
        "group_neighbors_1h": _squash(alarm_features["alarm_grp_prev_1h"], 5.0),
        "group_burst_24h": _squash(alarm_features["alarm_grp_prev_24h"], 20.0),
    }
    total = sum(w[k] for k in parts)
    return sum(w[k] * parts[k] for k in parts) / total


def hydraulic_load_anomaly(pump_features, weights=None):
    w = weights or HYDRAULIC_WEIGHTS
    rate_6h = pump_features["events_6h"].astype(float) / 6.0
    prior = pump_features["channel_event_prior"].astype(float) / 24.0
    load_z = (rate_6h - prior) / (np.sqrt(np.maximum(prior, 0.0)) + 1.0)
    parts = {
        "load_z": _squash(load_z, 2.0),
        "rapid_switching": _squash(pump_features["burst_count_24h"], 30.0),
        "burst_share": _squash(pump_features["events_1h"].astype(float) - prior, 10.0),
    }
    total = sum(w[k] for k in parts)
    return sum(w[k] * parts[k] for k in parts) / total
