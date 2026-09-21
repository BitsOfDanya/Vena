import time

import numpy as np
import pandas as pd

from pipeline import config, training
from pipeline import models as models_mod
from pipeline.formal import metrics as fm
from pipeline.sequence import gate_eval

DAILY_KEYS = ("avg_precision", "daily_precision_top_1pct", "alert_precision", "episode_recall",
              "median_lead_time_hours", "roc_auc")


def fold_layout(frame, fold):
    year = frame["ts"].dt.year
    train = (year <= fold["train_end"]).values
    valid = (year == fold["valid_year"]).values
    nxt = (year == fold["valid_year"] + 1).values
    return train, valid, nxt


def evaluate_scores(y, score, valid_frame, episodes, horizon_hours, target_name="target"):
    out = fm.frontier_metrics(y, score)
    frame = valid_frame.copy()
    frame["target"] = y
    daily = gate_eval.full_metrics(frame, score, episodes, horizon_hours)
    for key in DAILY_KEYS:
        if key in daily and key not in out:
            out[key] = daily[key]
    out["n"] = int(len(y))
    out["n_positive"] = int(np.sum(y))
    return out


def run_rolling(frame, episodes, fit_score, horizon_hours, label_col="target", folds=None, tag="",
                score_next=True, log=print):
    folds = folds or config.ROLLING_FOLDS
    rows = []
    scores = {}
    for fold in folds:
        train, valid, nxt = fold_layout(frame, fold)
        if valid.sum() == 0 or train.sum() == 0:
            continue
        use_next = score_next and nxt.sum() > 0
        score_mask = valid | nxt if use_next else valid
        t0 = time.time()
        all_scores = fit_score(frame, train, score_mask, fold)
        pos = np.flatnonzero(score_mask)
        s_valid = all_scores[np.isin(pos, np.flatnonzero(valid))]
        y_valid = frame.loc[valid, label_col].values
        vf = frame.loc[valid]
        y_main = frame.loc[valid, "target"].values
        row = evaluate_scores(y_main, s_valid, vf, episodes, horizon_hours)
        row.update(fold=fold["name"], tag=tag, seconds=round(time.time() - t0, 1))
        if use_next:
            s_next = all_scores[np.isin(pos, np.flatnonzero(nxt))]
            y_next = frame.loc[nxt, "target"].values
            tr = fm.transfer_metrics(y_main, s_valid, y_next, s_next)
            for k, v in tr.items():
                row[f"transfer_{k}"] = v
            fr_alert = fm.eval_at_threshold(y_main, s_valid, fm.pick_threshold(y_main, s_valid))["alert_fraction"]
            thr_q = float(np.quantile(s_next, 1.0 - fr_alert)) if fr_alert > 0 else float("inf")
            trf = fm.eval_at_threshold(y_next, s_next, thr_q)
            for k in ("precision", "recall", "formal_gap"):
                row[f"transfer_frac_{k}"] = trf[k]
        rows.append(row)
        scores[fold["name"]] = (frame.loc[valid, ["channel_id", "ts"]].assign(target=y_main, score=s_valid))
        log(f"{tag} {fold['name']}: AP={row['avg_precision']:.4f} top1={row['daily_precision_top_1pct']:.4f} "
            f"gap_oracle={row['formal_gap_oracle']:.3f} R@P.7={row['recall_at_precision_0.7']:.3f} "
            f"P@R.5={row['precision_at_recall_0.5']:.3f} ({row['seconds']}s)")
    return pd.DataFrame(rows), scores


def sklearn_fit_score(model_name, cols, label_col="target", params=None):
    def fn(frame, train, score_mask, fold):
        model = models_mod.MODEL_REGISTRY[model_name]() if params is None else models_mod.MODEL_REGISTRY[model_name](params)
        model.fit(frame.loc[train, cols], frame.loc[train, label_col])
        return model.predict_proba(frame.loc[score_mask, cols])
    return fn


def default_cols():
    return training.feature_columns()


def summarize(df, keys=("avg_precision", "daily_precision_top_1pct", "alert_precision", "episode_recall",
                        "recall_at_precision_0.7", "precision_at_recall_0.5", "pr_auc", "formal_gap_oracle",
                        "transfer_formal_gap", "transfer_precision", "transfer_recall")):
    cols = [k for k in keys if k in df.columns]
    return df[cols].agg(["mean", "min", "max"]).round(4)
