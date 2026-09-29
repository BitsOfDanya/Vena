import argparse
import csv
import json
import os
import urllib.request

import pandas as pd

from pipeline import config

POSITIVE = {"confirmed_issue", "maintenance_performed"}
NEGATIVE = {"no_issue_found", "false_or_irrelevant_signal"}
REPORT = os.path.join(config.ROOT, "results", "feedback_report.json")
LABELS = os.path.join(config.ROOT, "results", "feedback_labels.csv")
CSV_COLUMNS = {
    "Asset": "asset_id",
    "Scenario": "scenario",
    "Model": "model_id",
    "Score": "score",
    "Horizon (h)": "horizon_hours",
    "Prediction time (UTC)": "prediction_time",
    "Decision": "decision",
    "Outcome": "outcome",
}


def from_api(url):
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/v1/journal?limit=2000",
        headers={"X-API-Key": os.environ.get("VENA_API_KEY", "")},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return pd.DataFrame(json.load(response))


def from_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    frame = pd.DataFrame(rows).rename(columns=CSV_COLUMNS)
    for column in frame.columns:
        frame[column] = frame[column].astype(str).str.lstrip("'").replace({"": None})
    frame["score"] = pd.to_numeric(frame["score"], errors="coerce")
    return frame


def label(outcome):
    if outcome in POSITIVE:
        return 1
    if outcome in NEGATIVE:
        return 0
    return None


def summarize(journal):
    journal = journal.assign(label=journal["outcome"].map(label))
    decided = journal.dropna(subset=["label"])
    by_model = []
    for model_id, group in decided.groupby("model_id"):
        scores = pd.to_numeric(group["score"], errors="coerce")
        by_model.append({
            "model_id": model_id,
            "decided": int(len(group)),
            "confirmed_share": round(float(group["label"].mean()), 4),
            "mean_predicted_probability": round(float(scores.mean()), 4) if scores.notna().any() else None,
        })
    return {
        "forecasts": int(len(journal)),
        "decided": int(len(decided)),
        "confirmed": int((decided["label"] == 1).sum()),
        "rejected": int((decided["label"] == 0).sum()),
        "by_model": by_model,
    }, decided


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--url", help="service address, e.g. http://5.129.225.86")
    source.add_argument("--csv", help="CSV exported from the Journal page")
    arguments = parser.parse_args()

    journal = from_api(arguments.url) if arguments.url else from_csv(arguments.csv)
    report, decided = summarize(journal)
    with open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1, ensure_ascii=False)
    columns = [c for c in ("asset_id", "model_id", "scenario", "score", "horizon_hours", "prediction_time", "label")
               if c in decided.columns]
    decided[columns].to_csv(LABELS, index=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
