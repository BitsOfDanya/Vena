import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from pipeline.formal import twostage


def hard_negative_weights(frame, train_mask, cols, weight, mode="oof+near", oof_quantile=0.8):
    y = frame["target"].values
    weights = np.ones(len(frame))
    hard = np.zeros(len(frame), dtype=bool)
    if "oof" in mode:
        oof = twostage.temporal_oof(frame, train_mask, "logistic_regression", cols)
        thr = np.nanquantile(oof[train_mask], oof_quantile)
        hard |= (y == 0) & (oof >= thr)
    if "near" in mode:
        hard |= (y == 0) & (frame["y168"].values == 1)
    weights[hard & train_mask] = weight
    return weights


def fit_weighted_logreg(x, y, weights):
    scaler = StandardScaler()
    xs = scaler.fit_transform(x.fillna(-1))
    model = LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42)
    model.fit(xs, y, sample_weight=weights)
    return lambda z: model.predict_proba(scaler.transform(z.fillna(-1)))[:, 1]
