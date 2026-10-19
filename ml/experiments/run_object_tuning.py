import itertools
import json
import os
import sys
import time

import lightgbm as lgb
import pandas as pd

from experiments.run_object_selection import CHANNEL_CACHE, PARAMS, YEAR
from pipeline import context, incidents
from pipeline.formal import metrics as fm
from run_object_level import feature_sets, state_table

OUTPUT = os.path.join(os.path.dirname(__file__), "object_tuning.json")
GRID = {"num_leaves": (7, 15, 31), "min_child_samples": (20, 50, 200), "n_estimators": (150, 300, 600)}


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main():
    kinds = sys.argv[1:] or ["power", "flood", "fire"]
    object_of = context.locations()[0]
    registry = incidents.registry(object_of)
    table = state_table(registry, object_of)
    history_columns, state_columns = feature_sets(table)
    train = table["day"] < pd.Timestamp(f"{YEAR}-01-01") - pd.Timedelta(days=1)
    report = json.load(open(OUTPUT, encoding="utf-8")) if os.path.exists(OUTPUT) else {}
    for kind in kinds:
        keys = pd.read_parquet(os.path.join(CHANNEL_CACHE, f"object_selection_{kind}_{YEAR}.parquet"))[["key", "day"]]
        test = table.merge(keys.rename(columns={"key": "object"}), on=["object", "day"])
        y_train = table.loc[train, f"y_{kind}"].astype(int)
        y_test = test[f"y_{kind}"].astype(int).to_numpy()
        entry = {}
        for variant, columns in (("history", history_columns), ("state", state_columns)):
            results = []
            for leaves, child, trees in itertools.product(*GRID.values()):
                params = {**PARAMS, "num_leaves": leaves, "min_child_samples": child, "n_estimators": trees}
                model = lgb.LGBMClassifier(**params).fit(table.loc[train, columns], y_train)
                ap = fm.frontier_metrics(y_test, model.predict_proba(test[columns])[:, 1])["pr_auc"]
                results.append({"num_leaves": leaves, "min_child_samples": child, "n_estimators": trees, "avg_precision": round(float(ap), 4)})
            default = next(r for r in results if (r["num_leaves"], r["min_child_samples"], r["n_estimators"]) == (PARAMS["num_leaves"], PARAMS["min_child_samples"], PARAMS["n_estimators"]))
            best = max(results, key=lambda r: r["avg_precision"])
            entry[variant] = {"default": default, "best": best, "grid": results}
            log(f"{kind} {variant}: default AP {default['avg_precision']}, best {best}")
        report[kind] = entry
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
