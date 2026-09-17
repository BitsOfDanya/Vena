import os

import pandas as pd

import run_final_freeze as rff

DEVICES = {"pump": "Состояние насоса", "fan": "Состояние вентилятора", "smoke": "Датчик дыма"}

BASELINE_CONFIGS = [
    ("pump", 24, "catboost"),
    ("pump", 72, "logistic_regression"),
    ("fan", 24, "catboost"),
    ("fan", 72, "catboost"),
    ("smoke", 24, "catboost"),
]


def main():
    rows = []
    for device, horizon_hours, model_name in BASELINE_CONFIGS:
        rff.log(f"baseline suite {device} {horizon_hours}h {model_name} start")
        sensor_type = DEVICES[device]
        snapshot = rff.run_final_for_device(sensor_type, device, horizon_hours, model_name)

        daily_test = snapshot["daily_test"]
        alerts24 = snapshot["alerts"]["cooldown_24h"]
        formal = snapshot["formal_70_50"]
        max_recall = formal.get("max_recall_at_precision_0.7", {}).get("applied_on_test")
        max_precision = formal.get("max_precision_at_recall_0.5", {}).get("applied_on_test")

        rows.append({
            "device": device,
            "horizon": horizon_hours,
            "model": model_name,
            "roc_auc": snapshot["test"]["roc_auc"],
            "avg_precision": snapshot["test"]["avg_precision"],
            "daily_top1": daily_test["daily_precision_top_1pct"],
            "alert_precision": alerts24["alert_precision"],
            "episode_recall": alerts24["end_to_end_recall"],
            "median_lead_hours": alerts24["median_lead_time_hours"],
            "recall_at_precision_07": max_recall["recall"] if max_recall else None,
            "precision_at_recall_05": max_precision["precision"] if max_precision else None,
        })
        rff.log(f"baseline suite {device} {horizon_hours}h {model_name} done")

    os.makedirs("results", exist_ok=True)
    out = pd.DataFrame(rows)
    out.to_csv("results/baseline_metrics.csv", index=False)
    print(out.to_string(index=False))


if __name__ == "__main__":
    main()
