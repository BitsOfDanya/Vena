import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from pipeline import evaluate


def _normalize(s):
    s = np.asarray(s, dtype=float)
    lo, hi = s.min(), s.max()
    return (s - lo) / (hi - lo) if hi > lo else np.zeros_like(s)


def blend_search(scores_a, scores_b, y_true, weights=(0.0, 0.25, 0.5, 0.75, 1.0)):
    na, nb = _normalize(scores_a), _normalize(scores_b)
    results = []
    for w in weights:
        blended = w * na + (1 - w) * nb
        m = evaluate.evaluate(y_true, blended)
        m["w"] = w
        results.append(m)
    return pd.DataFrame(results)


def freeze_threshold_max_recall_at_precision(y_true, y_score, min_precision=0.7):
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    idx = np.where(precision[:-1] >= min_precision)[0]
    if len(idx) == 0:
        return None
    best = idx[np.argmax(recall[idx])]
    return {"threshold": float(thresholds[best]), "precision": float(precision[best]), "recall": float(recall[best])}


def freeze_threshold_max_precision_at_recall(y_true, y_score, min_recall=0.5):
    precision, recall, thresholds = precision_recall_curve(y_true, y_score)
    idx = np.where(recall[:-1] >= min_recall)[0]
    if len(idx) == 0:
        return None
    best = idx[np.argmax(precision[idx])]
    return {"threshold": float(thresholds[best]), "precision": float(precision[best]), "recall": float(recall[best])}


def apply_frozen_threshold(y_true, y_score, threshold):
    y_true = np.asarray(y_true)
    y_score = np.asarray(y_score)
    pred = (y_score >= threshold).astype(int)
    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {"threshold": threshold, "precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn}
