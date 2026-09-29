import pandas as pd

from pipeline import artifacts, calibration
from pipeline.ensemble import ProbabilityBlend
from pipeline.models import CatBoostModel, LogisticRegressionModel
from pipeline.targets.model_zoo import LightGBMModel

RECIPES = ("catboost", "lightgbm", "logistic_regression", "blend_lr_lightgbm")
LIGHTGBM_PARAMS = {"num_leaves": 31, "min_child_samples": 200}
BLEND_TREE_PARAMS = {"num_leaves": 7, "min_child_samples": 500}


def fit(recipe, features, target):
    if recipe == "catboost":
        return CatBoostModel().fit(features, target)
    if recipe == "lightgbm":
        return LightGBMModel(LIGHTGBM_PARAMS).fit(features, target)
    if recipe == "logistic_regression":
        return LogisticRegressionModel().fit(features, target)
    if recipe == "blend_lr_lightgbm":
        linear = LogisticRegressionModel().fit(features, target)
        tree = LightGBMModel(BLEND_TREE_PARAMS).fit(features, target)
        return ProbabilityBlend(linear, tree, linear_weight=0.5)
    raise ValueError(f"unknown recipe {recipe}")


def recipe_of(meta):
    config = meta["model_config"]
    return config.get("recipe") or config["model_name"]


def train_end_year(meta):
    return int(meta["training_period"]["train_years"].split("-")[-1])


def out_of_sample(name, frame, year, embargo_hours=168):
    model, meta = artifacts.load_artifact(name)
    if train_end_year(meta) < year:
        return model, artifacts.load_calibrator(name)
    columns = meta["feature_columns"]
    train = frame["ts"] < pd.Timestamp(f"{year - 1}-01-01") - pd.Timedelta(hours=embargo_hours)
    staging = fit(recipe_of(meta), frame.loc[train, columns], frame.loc[train, "target"])
    previous = frame["ts"].dt.year == year - 1
    calibrator = calibration.fit_isotonic(
        staging.predict_proba(frame.loc[previous, columns]), frame.loc[previous, "target"].values
    )
    return staging, calibrator
