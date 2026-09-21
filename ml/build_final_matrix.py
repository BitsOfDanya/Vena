import glob
import json
import os

import pandas as pd

from pipeline import artifacts

rows = []
for path in sorted(glob.glob("analysis/tables/final_snapshot_*.json")):
    name = os.path.basename(path).replace("final_snapshot_", "").replace(".json", "")
    device, horizon = name.rsplit("_", 1)
    with open(path) as f:
        d = json.load(f)

    artifact_name = f"{device}_{horizon}"
    _, meta = artifacts.load_artifact(artifact_name)
    cfg = {"model": meta["model_config"], "feature_columns": meta["feature_columns"]}

    os.makedirs("configs/models", exist_ok=True)
    with open(f"configs/models/{device}_{horizon}.json", "w") as f:
        json.dump({
            "device": device, "horizon": horizon, "model": meta["model_config"],
            "feature_columns": meta["feature_columns"], "artifact": artifact_name,
            "training_period": meta["training_period"], "version": meta["version"],
        }, f, indent=2, ensure_ascii=False)

    formal = d.get("formal_70_50", {})
    max_recall = formal.get("max_recall_at_precision_0.7", {}).get("applied_on_test")
    max_precision = formal.get("max_precision_at_recall_0.5", {}).get("applied_on_test")
    alerts24 = d.get("alerts", {}).get("cooldown_24h", {})
    fn = d.get("fn_breakdown", {})
    cal = d.get("calibration", {})

    rows.append({
        "device": device,
        "horizon_hours": horizon.replace("h", ""),
        "model": cfg["model"]["model_name"],
        "features": ",".join(cfg["feature_columns"][:3]) + f"...(+{len(cfg['feature_columns'])-3})",
        "candidate_policy": "alarm+fault_adjacent+recovery+burst+transition+silence",
        "chronic_policy": "none",
        "calibrated": False,
        "roc_auc_test": d["test"]["roc_auc"],
        "avg_precision_test": d["test"]["avg_precision"],
        "precision_at_recall_0.5_test": d["test"]["precision_at_recall_0.5"],
        "recall_at_precision_0.7_test": d["test"]["recall_at_precision_0.7"],
        "daily_precision_top1pct_test": d["daily_test"]["daily_precision_top_1pct"],
        "top10_per_day_precision_test": d["fixed_topk_test"]["precision_top10_per_day"],
        "top10_per_day_recall_test": d["fixed_topk_test"]["recall_top10_per_day"],
        "formal_max_recall_at_p07_precision": max_recall["precision"] if max_recall else None,
        "formal_max_recall_at_p07_recall": max_recall["recall"] if max_recall else None,
        "formal_max_precision_at_r05_precision": max_precision["precision"] if max_precision else None,
        "formal_max_precision_at_r05_recall": max_precision["recall"] if max_precision else None,
        "alert_precision_cooldown24h": alerts24.get("alert_precision"),
        "end_to_end_episode_recall_cooldown24h": alerts24.get("end_to_end_recall"),
        "alerts_per_day_cooldown24h": alerts24.get("alerts_per_day"),
        "median_lead_time_hours_cooldown24h": alerts24.get("median_lead_time_hours"),
        "candidate_generator_miss_share": fn.get("candidate_generator_miss_share"),
        "model_miss_share": fn.get("model_miss_share"),
        "brier_raw": cal.get("brier_raw"),
        "brier_calibrated": cal.get("brier_calibrated"),
        "ece_raw": cal.get("ece_raw"),
        "ece_calibrated": cal.get("ece_calibrated"),
    })

result = pd.DataFrame(rows).sort_values(["device", "horizon_hours"])
result.to_csv("analysis/tables/final_model_matrix.csv", index=False)
print(result.to_string(index=False))
