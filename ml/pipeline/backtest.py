import pandas as pd

from pipeline import config, models as models_mod, evaluate


def assign_fold(df, fold):
    year = df["ts"].dt.year
    train_mask = year <= fold["train_end"]
    if "valid_year" in fold:
        valid_mask = year == fold["valid_year"]
    else:
        valid_mask = (df["ts"] >= fold["valid_start"]) & (df["ts"] <= fold["valid_end"])
    out = df.copy()
    out["fold_split"] = "unused"
    out.loc[train_mask, "fold_split"] = "train"
    out.loc[valid_mask, "fold_split"] = "valid"
    return out


def run_fold(df, cols, model_names, fold):
    fdf = assign_fold(df, fold)
    train = fdf[fdf["fold_split"] == "train"]
    valid = fdf[fdf["fold_split"] == "valid"]
    results = []
    if valid.empty or valid["target"].sum() == 0 or train.empty:
        return pd.DataFrame(results)
    for name in model_names:
        model = models_mod.MODEL_REGISTRY[name]()
        model.fit(train[cols], train["target"])
        score = model.predict_proba(valid[cols])
        m = evaluate.evaluate(valid["target"].values, score)
        m.update(evaluate.evaluate_daily_topk(valid["ts"].values, valid["target"].values, score))
        m.update({"model": name, "fold": fold["name"], "n_train": len(train), "n_valid": len(valid)})
        results.append(m)
    return pd.DataFrame(results)


def run_rolling_backtest(df, cols, model_names, folds=None):
    folds = folds or config.ROLLING_FOLDS
    rows = [run_fold(df, cols, model_names, f) for f in folds]
    rows = [r for r in rows if not r.empty]
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True)


AGG_METRIC_COLUMNS = [
    "roc_auc", "avg_precision", "precision_at_recall_0.5", "recall_at_precision_0.7",
    "daily_precision_top_1pct", "daily_recall_top_1pct",
]


def aggregate_backtest(results, metric_cols=None):
    metric_cols = metric_cols or AGG_METRIC_COLUMNS
    agg_rows = []
    if results.empty:
        return pd.DataFrame(agg_rows)
    for model_name, g in results.groupby("model"):
        row = {"model": model_name, "n_folds": len(g)}
        for col in metric_cols:
            vals = g[col].dropna()
            row[f"{col}_mean"] = vals.mean() if len(vals) else None
            row[f"{col}_median"] = vals.median() if len(vals) else None
            row[f"{col}_std"] = vals.std() if len(vals) else None
            row[f"{col}_worst"] = vals.min() if len(vals) else None
        agg_rows.append(row)
    return pd.DataFrame(agg_rows)
