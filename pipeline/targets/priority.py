import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {"equipment_failure": 0.35, "power_failure": 0.25, "sensor_failure": 0.15,
                   "alarm_confidence": 0.15, "anomaly": 0.10}


def rank_normalize(values):
    s = pd.Series(np.asarray(values, dtype=float))
    return s.rank(pct=True, na_option="keep").values


def maintenance_priority(signals, weights=None):
    w = weights or DEFAULT_WEIGHTS
    names = [k for k in w if k in signals]
    if not names:
        raise ValueError("no known signals")
    mat = np.column_stack([rank_normalize(signals[k]) for k in names])
    wv = np.array([w[k] for k in names], dtype=float)
    avail = ~np.isnan(mat)
    weighted = np.where(avail, mat, 0.0) * wv
    denom = (avail * wv).sum(axis=1)
    score = np.where(denom > 0, weighted.sum(axis=1) / np.where(denom > 0, denom, 1.0), np.nan)
    contrib = pd.DataFrame(weighted / np.where(denom > 0, denom, 1.0)[:, None], columns=names)
    top = contrib.idxmax(axis=1).where(denom > 0)
    return pd.DataFrame({"priority": score, "top_reason": top.values, "signals_available": avail.sum(axis=1)})
