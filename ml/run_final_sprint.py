import sys
import time

from pipeline import config, experiments

BASE_MODELS = ["logistic_regression", "catboost"]

CATBOOST_GRID = [
    {},
    {"depth": 4},
    {"depth": 8},
    {"learning_rate": 0.04},
    {"learning_rate": 0.15},
    {"l2_leaf_reg": 10.0},
    {"bagging_temperature": 0.5},
    {"random_strength": 3.0},
]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run_device_stage1(sensor_type, tag):
    log(f"{tag} candidate_trigger_ablation start")
    experiments.candidate_trigger_ablation(
        sensor_type, ["logistic_regression"], f"analysis/tables/candidate_trigger_ablation_{tag}.csv",
    )
    log(f"{tag} candidate_trigger_ablation done")

    log(f"{tag} rolling_backtest 24h start")
    experiments.rolling_backtest_device(
        sensor_type, BASE_MODELS, f"analysis/tables/rolling_backtest_{tag}_24h.csv", horizon_hours=24,
    )
    log(f"{tag} rolling_backtest 24h done")

    log(f"{tag} rolling_backtest 72h start")
    experiments.rolling_backtest_device(
        sensor_type, BASE_MODELS, f"analysis/tables/rolling_backtest_{tag}_72h.csv", horizon_hours=72,
    )
    log(f"{tag} rolling_backtest 72h done")

    if sensor_type in config.DUTY_CYCLE_SENSOR_TYPES:
        log(f"{tag} rolling_backtest duty_cycle start")
        experiments.rolling_backtest_device(
            sensor_type, BASE_MODELS, f"analysis/tables/rolling_backtest_{tag}_24h_duty.csv",
            horizon_hours=24, with_duty_cycle=True,
        )
        log(f"{tag} rolling_backtest duty_cycle done")

    log(f"{tag} chronic_quantile_rolling_check start")
    experiments.chronic_quantile_rolling_check(
        sensor_type, BASE_MODELS, f"analysis/tables/chronic_quantile_rolling_{tag}.csv",
    )
    log(f"{tag} chronic_quantile_rolling_check done")


def run_device_stage2(sensor_type, tag):
    ctx = experiments.DeviceContext(sensor_type)
    df24 = ctx.build(horizon_hours=24)
    cols = experiments.training.feature_columns()

    log(f"{tag} ranking_comparison start")
    from pipeline import ranking
    ranking.run_ranking_comparison(df24, cols, f"analysis/tables/ranking_comparison_{tag}.csv")
    log(f"{tag} ranking_comparison done")

    log(f"{tag} ensemble_blend start")
    from pipeline import decision, models as m
    valid = df24[df24["split"] == "valid"]
    test = df24[df24["split"] == "test"]
    train = df24[df24["split"] == "train"]
    logreg = m.LogisticRegressionModel().fit(train[cols], train["target"])
    catboost = m.CatBoostModel().fit(train[cols], train["target"])
    valid_a, valid_b = logreg.predict_proba(valid[cols]), catboost.predict_proba(valid[cols])
    blend_valid = decision.blend_search(valid_a, valid_b, valid["target"].values)
    blend_valid["split"] = "valid"
    test_a, test_b = logreg.predict_proba(test[cols]), catboost.predict_proba(test[cols])
    blend_test = decision.blend_search(test_a, test_b, test["target"].values)
    blend_test["split"] = "test"
    import pandas as pd
    pd.concat([blend_valid, blend_test], ignore_index=True).to_csv(f"analysis/tables/ensemble_blend_{tag}.csv", index=False)
    log(f"{tag} ensemble_blend done")


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"
    device_arg = sys.argv[2] if len(sys.argv) > 2 else None

    devices = [("Состояние насоса", "pump"), ("Состояние вентилятора", "fan"), ("Датчик дыма", "smoke")]
    if device_arg:
        devices = [(st, tg) for st, tg in devices if tg == device_arg]

    if stage in ("all", "stage1"):
        for sensor_type, tag in devices:
            run_device_stage1(sensor_type, tag)

    if stage in ("all", "stage2"):
        for sensor_type, tag in devices:
            run_device_stage2(sensor_type, tag)

    if stage in ("all", "hp_pump"):
        log("hp_search pump start")
        grid = [dict(p) for p in CATBOOST_GRID]
        experiments.hyperparameter_search(
            "Состояние насоса", grid, "analysis/tables/hp_search_catboost_pump.csv",
        )
        log("hp_search pump done")


if __name__ == "__main__":
    main()
