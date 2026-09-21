import numpy as np

from pipeline import models as models_mod


def _fit_predict(model_name, frame, cols, label_col, fit_mask, pred_mask):
    model = models_mod.MODEL_REGISTRY[model_name]()
    model.fit(frame.loc[fit_mask, cols], frame.loc[fit_mask, label_col])
    return model.predict_proba(frame.loc[pred_mask, cols])


def temporal_oof(frame, train_mask, model_name, cols, label_col="target"):
    year = frame["ts"].dt.year.values
    years = sorted(set(year[train_mask]))
    oof = np.full(len(frame), np.nan)
    for y in years[1:]:
        fit_mask = train_mask & (year < y)
        pred_mask = train_mask & (year == y)
        oof[pred_mask] = _fit_predict(model_name, frame, cols, label_col, fit_mask, pred_mask)
    return oof


def pool_threshold(oof, y, train_mask, target_pool_recall):
    valid_rows = train_mask & ~np.isnan(oof)
    s = oof[valid_rows]
    yy = y[valid_rows]
    order = np.argsort(-s)
    cum = np.cumsum(yy[order]) / max(yy.sum(), 1)
    k = int(np.searchsorted(cum, target_pool_recall))
    k = min(k, len(s) - 1)
    return float(s[order[k]])


def two_stage_fit_score(stage1_name, stage2_name, cols, pool_recall=0.85, label_col="target"):
    def fn(frame, train, score_mask, fold):
        y = frame[label_col].values
        oof = temporal_oof(frame, train, stage1_name, cols, label_col)
        thr = pool_threshold(oof, y, train, pool_recall)
        s1_all = _fit_predict(stage1_name, frame, cols, label_col, train, train | score_mask)
        pos_all = np.flatnonzero(train | score_mask)
        s1 = np.full(len(frame), np.nan)
        s1[pos_all] = s1_all
        s1_oof_or_pred = np.where(np.isnan(oof), s1, oof)
        stage2_frame = frame.copy()
        stage2_frame["_s1"] = s1_oof_or_pred
        cols2 = cols + ["_s1"]
        pool_train = train & ~np.isnan(oof) & (oof >= thr)
        model = models_mod.MODEL_REGISTRY[stage2_name]()
        model.fit(stage2_frame.loc[pool_train, cols2], stage2_frame.loc[pool_train, label_col])
        stage2_frame["_s1"] = s1
        in_pool = score_mask & (s1 >= thr)
        out = np.full(len(frame), np.nan)
        out[score_mask] = s1[score_mask] * 1e-3
        if in_pool.any():
            out[in_pool] = 1.0 + model.predict_proba(stage2_frame.loc[in_pool, cols2])
        fn.last_info = dict(threshold=thr, pool_fraction_train=float(pool_train.sum() / max((train & ~np.isnan(oof)).sum(), 1)),
                            pool_recall_valid=float(frame.loc[in_pool, label_col].sum() / max(frame.loc[score_mask & (frame["ts"].dt.year == fold["valid_year"]).values, label_col].sum(), 1)))
        return out[score_mask]
    return fn
