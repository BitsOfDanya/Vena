import pandas as pd

from pipeline import features as features_mod, models, evaluate


def feature_columns(with_neighbors=False, with_weather=False, with_duty_cycle=False):
    cols = list(features_mod.FEATURE_COLUMNS)
    if with_neighbors:
        cols += features_mod.NEIGHBOR_FEATURE_COLUMNS
    if with_weather:
        cols += features_mod.WEATHER_FEATURE_COLUMNS
    if with_duty_cycle:
        cols += features_mod.DUTY_CYCLE_FEATURE_COLUMNS
    return cols


def run_models(df, cols, model_names):
    train = df[df["split"] == "train"]
    valid = df[df["split"] == "valid"]
    test = df[df["split"] == "test"]

    results = []
    for name in model_names:
        model = models.MODEL_REGISTRY[name]()
        model.fit(train[cols], train["target"])
        for split_name, split_df in [("valid", valid), ("test", test)]:
            if split_df.empty or split_df["target"].sum() == 0:
                continue
            score = model.predict_proba(split_df[cols])
            metrics = evaluate.evaluate(split_df["target"].values, score)
            metrics.update(evaluate.evaluate_daily_topk(split_df["ts"].values, split_df["target"].values, score))
            metrics.update({"model": name, "split": split_name})
            results.append(metrics)
    return pd.DataFrame(results)
