import sys
import time

from pipeline import config, experiments

BASE_MODELS = ["logistic_regression", "hist_gradient_boosting", "catboost"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main():
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"

    if stage in ("all", "device"):
        log("device_comparison start")
        experiments.device_comparison(
            BASE_MODELS, "analysis/tables/device_model_comparison.csv",
            sensor_types=[t for t in config.DEVICE_TYPES if t != "Газовый датчик"],
        )
        log("device_comparison done")

    if stage in ("all", "horizon"):
        log("horizon_comparison start")
        experiments.horizon_comparison(
            config.PRIMARY_DEVICE_TYPES + config.SECONDARY_DEVICE_TYPES,
            BASE_MODELS, "analysis/tables/horizon_comparison.csv",
        )
        log("horizon_comparison done")

    if stage in ("all", "chronic_pump"):
        log("chronic pump start")
        experiments.chronic_channel_comparison(
            "Состояние насоса", BASE_MODELS, "analysis/tables/chronic_channel_pump.csv",
        )
        log("chronic pump done")

    if stage in ("all", "chronic_fan"):
        log("chronic fan start")
        experiments.chronic_channel_comparison(
            "Состояние вентилятора", BASE_MODELS, "analysis/tables/chronic_channel_fan.csv",
        )
        log("chronic fan done")

    if stage in ("all", "storm"):
        log("storm ablation start")
        experiments.storm_2021_ablation(
            "Состояние насоса", BASE_MODELS, "analysis/tables/storm_2021_ablation.csv",
        )
        log("storm ablation done")

    if stage in ("all", "weather"):
        log("weather ablation start")
        experiments.weather_ablation(
            "Состояние насоса", BASE_MODELS, "analysis/tables/weather_ablation.csv",
        )
        log("weather ablation done")

    if stage in ("all", "neighbor"):
        log("neighbor ablation start")
        experiments.neighbor_ablation(
            "Состояние насоса", BASE_MODELS, "analysis/tables/neighbor_ablation.csv",
        )
        log("neighbor ablation done")

    if stage in ("all", "full4_pump"):
        log("full 4-model pump start")
        experiments.device_comparison(
            BASE_MODELS + ["xgboost"], "analysis/tables/full_model_comparison_pump.csv",
            sensor_types=["Состояние насоса"],
        )
        log("full 4-model pump done")

    if stage in ("all", "full4_fan"):
        log("full 4-model fan start")
        experiments.device_comparison(
            BASE_MODELS + ["xgboost"], "analysis/tables/full_model_comparison_fan.csv",
            sensor_types=["Состояние вентилятора"],
        )
        log("full 4-model fan done")

    if stage in ("round2", "storm_smoke"):
        log("storm ablation smoke start")
        experiments.storm_2021_ablation(
            "Датчик дыма", BASE_MODELS, "analysis/tables/storm_2021_ablation_smoke.csv",
        )
        log("storm ablation smoke done")

    if stage in ("round2", "storm_fan"):
        log("storm ablation fan start")
        experiments.storm_2021_ablation(
            "Состояние вентилятора", BASE_MODELS, "analysis/tables/storm_2021_ablation_fan.csv",
        )
        log("storm ablation fan done")

    if stage in ("round2", "weather_smoke"):
        log("weather ablation smoke start")
        experiments.weather_ablation(
            "Датчик дыма", BASE_MODELS, "analysis/tables/weather_ablation_smoke.csv",
        )
        log("weather ablation smoke done")

    if stage in ("round2", "weather_fan"):
        log("weather ablation fan start")
        experiments.weather_ablation(
            "Состояние вентилятора", BASE_MODELS, "analysis/tables/weather_ablation_fan.csv",
        )
        log("weather ablation fan done")

    if stage in ("round2", "neighbor_smoke"):
        log("neighbor ablation smoke start")
        experiments.neighbor_ablation(
            "Датчик дыма", BASE_MODELS, "analysis/tables/neighbor_ablation_smoke.csv",
        )
        log("neighbor ablation smoke done")

    if stage in ("round2", "neighbor_fan"):
        log("neighbor ablation fan start")
        experiments.neighbor_ablation(
            "Состояние вентилятора", BASE_MODELS, "analysis/tables/neighbor_ablation_fan.csv",
        )
        log("neighbor ablation fan done")

    if stage in ("round2", "chronic_pump_quantile"):
        log("chronic pump quantile start")
        experiments.chronic_channel_comparison_by_quantile(
            "Состояние насоса", BASE_MODELS, "analysis/tables/chronic_channel_pump_quantile.csv",
            quantile=0.5,
        )
        log("chronic pump quantile done")

    if stage == "gas_full":
        log("gas full pipeline start")
        experiments.device_comparison(
            BASE_MODELS, "analysis/tables/gas_device_comparison.csv",
            sensor_types=["Газовый датчик"],
        )
        log("gas full pipeline done")


if __name__ == "__main__":
    main()
