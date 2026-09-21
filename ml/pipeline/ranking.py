import numpy as np
import pandas as pd

from pipeline import evaluate


class CatBoostRankerModel:
    name = "catboost_ranker"

    def __init__(self):
        from catboost import CatBoostRanker
        self.model = CatBoostRanker(
            iterations=300, learning_rate=0.08, depth=6, loss_function="YetiRank",
            verbose=False, random_seed=42,
        )

    def fit(self, X, y, group_id):
        from catboost import Pool
        order = np.argsort(group_id, kind="stable")
        pool = Pool(X.iloc[order].fillna(-1), label=np.asarray(y)[order], group_id=np.asarray(group_id)[order])
        self.model.fit(pool)
        return self

    def predict_proba(self, X):
        return self.model.predict(X.fillna(-1))


class XGBRankerModel:
    name = "xgboost_ranker"

    def __init__(self):
        from xgboost import XGBRanker
        self.model = XGBRanker(
            n_estimators=300, learning_rate=0.08, max_depth=6,
            objective="rank:pairwise", random_state=42, n_jobs=6,
        )

    def fit(self, X, y, group_id):
        order = np.argsort(group_id, kind="stable")
        group_sizes = pd.Series(np.asarray(group_id)[order]).value_counts().sort_index().values
        self.model.fit(X.iloc[order].fillna(-1), np.asarray(y)[order], group=group_sizes)
        return self

    def predict_proba(self, X):
        return self.model.predict(X.fillna(-1))


RANKER_REGISTRY = {"catboost_ranker": CatBoostRankerModel, "xgboost_ranker": XGBRankerModel}


def run_ranking_comparison(df, cols, out_path, ranker_names=None):
    ranker_names = ranker_names or list(RANKER_REGISTRY)
    train = df[df["split"] == "train"]
    valid = df[df["split"] == "valid"]
    test = df[df["split"] == "test"]
    train_group = train["ts"].dt.floor("D").astype("int64")

    results = []
    for name in ranker_names:
        model = RANKER_REGISTRY[name]()
        model.fit(train[cols], train["target"], train_group.values)
        for split_name, split_df in [("valid", valid), ("test", test)]:
            if split_df.empty or split_df["target"].sum() == 0:
                continue
            score = model.predict_proba(split_df[cols])
            metrics = evaluate.evaluate(split_df["target"].values, score)
            metrics.update(evaluate.evaluate_daily_topk(split_df["ts"].values, split_df["target"].values, score))
            metrics.update({"model": name, "split": split_name})
            results.append(metrics)
    result = pd.DataFrame(results)
    result.to_csv(out_path, index=False)
    return result
