from lightgbm import LGBMClassifier


class LightGBMModel:
    name = "lightgbm"

    def __init__(self, params=None):
        params = params or {}
        self.model = LGBMClassifier(
            n_estimators=params.get("n_estimators", 300), learning_rate=params.get("learning_rate", 0.08),
            num_leaves=params.get("num_leaves", 63), min_child_samples=params.get("min_child_samples", 100),
            subsample=0.8, subsample_freq=1, colsample_bytree=0.8, class_weight="balanced",
            random_state=42, n_jobs=params.get("n_jobs", 6), verbose=-1,
        )

    def fit(self, X, y):
        self.model.fit(X.fillna(-1), y)
        return self

    def predict_proba(self, X):
        return self.model.predict_proba(X.fillna(-1))[:, 1]


class ColumnPriorModel:
    name = "prior"

    def __init__(self, column, sign=1.0):
        self.column = column
        self.sign = sign

    def fit(self, X, y):
        return self

    def predict_proba(self, X):
        return self.sign * X[self.column].fillna(-1).values.astype(float)
