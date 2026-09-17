import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.preprocessing import StandardScaler


class LogisticRegressionModel:
    name = "logistic_regression"

    def __init__(self, params=None):
        params = params or {}
        self.scaler = StandardScaler()
        self.model = LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=42,
            C=params.get("C", 1.0), penalty=params.get("penalty", "l2"),
        )

    def fit(self, X, y):
        Xs = self.scaler.fit_transform(X.fillna(-1))
        self.model.fit(Xs, y)
        return self

    def predict_proba(self, X):
        Xs = self.scaler.transform(X.fillna(-1))
        return self.model.predict_proba(Xs)[:, 1]


class HistGBModel:
    name = "hist_gradient_boosting"

    def __init__(self):
        self.model = HistGradientBoostingClassifier(max_iter=200, learning_rate=0.08, max_depth=6, random_state=42)

    def fit(self, X, y):
        weight = np.where(y == 1, max((len(y) - y.sum()) / max(y.sum(), 1), 1.0), 1.0)
        self.model.fit(X, y, sample_weight=weight)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(X)[:, 1]


class CatBoostModel:
    name = "catboost"

    def __init__(self, params=None):
        params = params or {}
        from catboost import CatBoostClassifier
        self.model = CatBoostClassifier(
            iterations=params.get("iterations", 300),
            learning_rate=params.get("learning_rate", 0.08),
            depth=params.get("depth", 6),
            l2_leaf_reg=params.get("l2_leaf_reg", 3.0),
            random_strength=params.get("random_strength", 1.0),
            bagging_temperature=params.get("bagging_temperature", 1.0),
            auto_class_weights="Balanced",
            verbose=False, random_seed=42,
        )

    def fit(self, X, y):
        self.model.fit(X.fillna(-1), y)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(X.fillna(-1))[:, 1]


class XGBoostModel:
    name = "xgboost"

    def __init__(self):
        from xgboost import XGBClassifier
        self.model = XGBClassifier(
            n_estimators=300, learning_rate=0.08, max_depth=6,
            eval_metric="aucpr", random_state=42, n_jobs=6,
        )

    def fit(self, X, y):
        pos = max(y.sum(), 1)
        neg = len(y) - pos
        self.model.set_params(scale_pos_weight=neg / pos)
        self.model.fit(X.fillna(-1), y)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(X.fillna(-1))[:, 1]


MODEL_REGISTRY = {
    "logistic_regression": LogisticRegressionModel,
    "hist_gradient_boosting": HistGBModel,
    "catboost": CatBoostModel,
    "xgboost": XGBoostModel,
}
