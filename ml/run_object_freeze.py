import json
import os
import sys
import time

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from experiments.run_object_selection import PARAMS, VARIANTS, channel_daily
from pipeline import artifacts, calibration, config, context, incidents, object_risk
from run_object_level import feature_sets, state_table

SELECTION = os.path.join(config.ROOT, "experiments", "object_selection.json")
OBJECT_LEVEL = os.path.join(config.ROOT, "results", "object_level.json")
TEST_VARIANT = {"history": "history_model", "state": "state_model", "blend": "blend"}
FEATURES_TEXT = {
    "history": "число инцидентов объекта каждого типа за 1, 7, 30, 90 суток, сутки с последнего, месяц, день недели",
    "state": "история инцидентов объекта и число состояний его каналов за 1, 7, 30 суток: обесточен, неисправен, затоплен, обнаружен дым",
}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def quantiles(values):
    return np.quantile(np.asarray(values, dtype=float), np.linspace(0, 1, 2001))


def main():
    kinds = sys.argv[1:] or list(object_risk.KINDS)
    selection = json.load(open(SELECTION, encoding="utf-8"))["variants"]
    level = json.load(open(OBJECT_LEVEL, encoding="utf-8"))["incidents"]
    object_of = context.locations()[0]
    registry = incidents.registry(object_of)
    rules = incidents.rules()
    table = state_table(registry, object_of)
    history_columns, state_columns = feature_sets(table)
    for kind in kinds:
        chosen = selection[kind]
        variant = chosen["selected"]
        if variant not in TEST_VARIANT or chosen[variant]["avg_precision"] <= chosen["rule"]["avg_precision"]:
            log(f"{kind}: на 2025 выбран вариант {chosen['selected']}, модель объекта в прод не идёт")
            continue
        scenario, name, source = object_risk.KINDS[kind]
        columns = state_columns if variant == "state" else history_columns
        y = table[f"y_{kind}"].astype(int)
        staging_rows = table["day"] < pd.Timestamp("2024-12-31")
        params = chosen.get("params", {}).get("state" if variant == "state" else "history", PARAMS)
        staging = lgb.LGBMClassifier(**params).fit(table.loc[staging_rows, columns], y[staging_rows])
        year = table.loc[table["day"].dt.year == 2025, ["object", "day", *columns]]
        year = year.assign(history=staging.predict_proba(year[columns])[:, 1], target=y[year.index].to_numpy())
        reference = None
        if variant != "blend":
            calibrator = calibration.fit_isotonic(year["history"].to_numpy(), year["target"].to_numpy())
        else:
            base = channel_daily(kind, registry, object_of)
            merged = base.merge(year[["object", "day", "history"]].rename(columns={"object": "key"}), on=["key", "day"])
            reference = {"channel": quantiles(merged["channel"]), "history": quantiles(merged["history"])}
            blend = object_risk.ecdf(merged["channel"], reference["channel"]) + object_risk.ecdf(merged["history"], reference["history"])
            calibrator = calibration.fit_isotonic(blend, merged["target"].to_numpy())
            log(f"{kind}: смесь на 2025, объекто-суток {len(merged)}, доля инцидентов {merged['target'].mean():.4f}")
        final_rows = table["day"] < pd.Timestamp("2025-12-31")
        model = lgb.LGBMClassifier(**params).fit(table.loc[final_rows, columns], y[final_rows])
        ece = None
        if variant != "blend":
            rows = (table["day"] >= pd.Timestamp("2026-01-02")) & (table["day"] <= pd.Timestamp("2026-06-29"))
            probability = calibration.apply_isotonic(calibrator, model.predict_proba(table.loc[rows, columns])[:, 1])
            ece = round(float(calibration.expected_calibration_error(y[rows].to_numpy(), probability)[0]), 4)
        variants = level[kind]["variants"]
        test = variants[TEST_VARIANT[variant]]
        metrics = {
            "selection_2025": {v: {k: chosen[v][k] for k in ("avg_precision", "base_rate", "top_k")} for v in VARIANTS if v in chosen},
            "test_2026h1": {"avg_precision": test["avg_precision"], "roc_auc": test["roc_auc"], "base_rate": test["base_rate"],
                            "top3": test["top_k"]["3"], "top5": test["top_k"]["5"], "ece": ece,
                            "recall_top3": test["recall_top_k"]["3"], "recall_at_precision_0_7": test["recall_at_precision_0_7"],
                            "rule_avg_precision": variants["rule_7d"]["avg_precision"],
                            "channel_avg_precision": variants["channel_model"]["avg_precision"],
                            "history_avg_precision": variants["history_model"]["avg_precision"],
                            "state_avg_precision": variants.get("state_model", {}).get("avg_precision")},
        }
        model_config = {"label": rules[kind]["label"], "rule": rules[kind]["rule"], "kind": kind, "scenario": scenario, "recipe": "lightgbm",
                        "calibration": {"method": "isotonic", "fit_period": "2025"},
                        "variant": variant, "source_model": source, "horizon_hours": 24, "calibrated": True,
                        "target": "инцидент реестра на объекте в течение суток", "features": FEATURES_TEXT.get(variant, FEATURES_TEXT["history"])}
        artifacts.save_artifact(name, model, columns, model_config, {"train_years": f"{config.TRAIN_YEARS[0]}-2025"}, metrics,
                                version=time.strftime("%Y-%m-%d"))
        joblib.dump(calibrator, os.path.join(artifacts.artifact_dir(name), "calibrator.joblib"))
        if reference is not None:
            np.savez(object_risk.reference_path(name), **reference)
        log(f"{kind}: {name} ({variant}) сохранена, 2026H1 AP {test['avg_precision']} при правиле {variants['rule_7d']['avg_precision']}")


if __name__ == "__main__":
    main()
