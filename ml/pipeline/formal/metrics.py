import numpy as np
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
)

TARGET_PRECISION = 0.70
TARGET_RECALL = 0.50
RECALL_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6)
PRECISION_LEVELS = (0.5, 0.6, 0.7, 0.8)


def formal_gap(precision, recall):
    return max(TARGET_PRECISION - precision, 0.0) + max(TARGET_RECALL - recall, 0.0)


def _curve(y, score):
    p, r, thr = precision_recall_curve(y, score)
    return p[:-1], r[:-1], thr


def _gaps(p, r):
    return np.maximum(TARGET_PRECISION - p, 0.0) + np.maximum(TARGET_RECALL - r, 0.0)


def frontier_metrics(y, score):
    y = np.asarray(y)
    score = np.asarray(score)
    p, r, _ = _curve(y, score)
    out = {
        "pr_auc": float(average_precision_score(y, score)),
        "roc_auc": float(roc_auc_score(y, score)),
    }
    for level in RECALL_LEVELS:
        mask = r >= level
        out[f"precision_at_recall_{level}"] = float(p[mask].max()) if mask.any() else 0.0
    for level in PRECISION_LEVELS:
        mask = p >= level
        out[f"recall_at_precision_{level}"] = float(r[mask].max()) if mask.any() else 0.0
    denom_f1 = np.where(p + r > 0, p + r, 1.0)
    denom_f2 = np.where(4 * p + r > 0, 4 * p + r, 1.0)
    out["best_f1"] = float((2 * p * r / denom_f1).max())
    out["best_f2"] = float((5 * p * r / denom_f2).max())
    gaps = _gaps(p, r)
    i = int(np.argmin(gaps))
    out["formal_gap_oracle"] = float(gaps[i])
    out["oracle_precision"] = float(p[i])
    out["oracle_recall"] = float(r[i])
    out["formal_reached_oracle"] = bool(((p > TARGET_PRECISION) & (r > TARGET_RECALL)).any())
    return out


def pick_threshold(y_valid, score_valid):
    y_valid = np.asarray(y_valid)
    score_valid = np.asarray(score_valid)
    p, r, thr = _curve(y_valid, score_valid)
    gaps = _gaps(p, r)
    f1 = 2 * p * r / np.where(p + r > 0, p + r, 1.0)
    order = np.lexsort((-f1, gaps))
    return float(thr[order[0]])


def eval_at_threshold(y, score, threshold):
    y = np.asarray(y)
    pred = np.asarray(score) >= threshold
    tp = int((pred & (y == 1)).sum())
    n_pred = int(pred.sum())
    n_pos = int((y == 1).sum())
    precision = tp / n_pred if n_pred else 0.0
    recall = tp / n_pos if n_pos else 0.0
    return {
        "threshold": float(threshold),
        "tp": tp,
        "fp": n_pred - tp,
        "fn": n_pos - tp,
        "precision": precision,
        "recall": recall,
        "formal_gap": formal_gap(precision, recall),
        "alert_fraction": n_pred / len(y) if len(y) else 0.0,
        "formal_reached": bool(precision > TARGET_PRECISION and recall > TARGET_RECALL),
    }


def transfer_metrics(y_valid, score_valid, y_test, score_test):
    thr = pick_threshold(y_valid, score_valid)
    return eval_at_threshold(y_test, score_test, thr)
