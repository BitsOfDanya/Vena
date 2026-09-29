import json
import os
import sys
import time

import pandas as pd

from pipeline import artifacts, context, recipes
from pipeline.formal import metrics as fm
from pipeline import evaluate
from run_refit_study import current_window, frames, training_rows

OUTPUT = os.path.join(os.path.dirname(__file__), "context_features.json")


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def summary(target, score, ts):
    frontier = fm.frontier_metrics(target, score)
    top = evaluate.evaluate_daily_topk_fixed(ts, target, score, counts=(5,))
    return {"avg_precision": round(float(frontier["pr_auc"]), 4), "roc_auc": round(float(frontier["roc_auc"]), 4),
            "top5_per_day": top["precision_top5_per_day"]}


def main() -> None:
    names = sys.argv[1:] or ["pump_24h", "pump_72h", "fan_24h", "fan_72h", "smoke_24h", "flood_24h", "phase_24h"]
    object_of, section_of = context.locations()
    report = json.load(open(OUTPUT, encoding="utf-8")) if os.path.exists(OUTPUT) else {}
    for name, frame, horizon in frames(names):
        meta = artifacts.load_artifact(name)[1]
        base = meta["feature_columns"]
        recipe, window = recipes.recipe_of(meta), current_window(meta)
        frame = frame.reset_index(drop=True)
        started = time.time()
        extra = context.features(frame[["channel_id", "ts"]], object_of, section_of)
        frame = pd.concat([frame, extra], axis=1)
        log(f"{name}: {len(extra.columns)} context features in {time.time() - started:.0f}s")
        year = frame["ts"].dt.year
        periods = {
            "2025": (training_rows(frame, 2025, window), year == 2025),
            "2026H1": (training_rows(frame, 2026, window),
                       (year == 2026) & (frame["ts"] <= frame["ts"].max() - pd.Timedelta(hours=horizon))),
        }
        result = {"recipe": recipe, "window": window}
        for period, (train, test) in periods.items():
            train, test = train.to_numpy(), test.to_numpy()
            y, ts = frame.loc[test, "target"].to_numpy(), frame.loc[test, "ts"].to_numpy()
            for label, columns in (("base", base), ("context", base + list(extra.columns))):
                model = recipes.fit(recipe, frame.loc[train, columns], frame.loc[train, "target"])
                result[f"{period}_{label}"] = summary(y, model.predict_proba(frame.loc[test, columns]), ts)
                log(f"{name} {period} {label}: {result[f'{period}_{label}']}")
                if label == "context" and period == "2026H1" and hasattr(model, "model") and hasattr(model.model, "feature_importances_"):
                    importance = pd.Series(model.model.feature_importances_, index=columns).sort_values(ascending=False)
                    result["top_features_2026H1"] = {k: round(float(v), 2) for k, v in importance.head(12).items()}
        report[name] = result
        with open(OUTPUT, "w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
