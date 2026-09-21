import numpy as np
import pandas as pd

from pipeline.targets import model_zoo


def test_lightgbm_model_learns_a_simple_signal():
    rng = np.random.default_rng(0)
    x = pd.DataFrame({"a": rng.normal(size=3000), "b": rng.normal(size=3000)})
    y = (x["a"] + 0.2 * rng.normal(size=3000) > 0.5).astype(int)
    m = model_zoo.LightGBMModel({"n_estimators": 60, "n_jobs": 1}).fit(x, y)
    p = m.predict_proba(x)
    assert p[y == 1].mean() > p[y == 0].mean() + 0.3


def test_column_prior_model_ranks_by_column_with_sign():
    x = pd.DataFrame({"c": [1.0, 3.0, 2.0]})
    assert model_zoo.ColumnPriorModel("c").predict_proba(x).argsort().tolist() == [0, 2, 1]
    assert model_zoo.ColumnPriorModel("c", -1.0).predict_proba(x).argsort().tolist() == [1, 2, 0]
