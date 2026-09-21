import json
import os

import joblib

from pipeline import config


def artifact_dir(name):
    return os.path.join(config.ROOT, "artifacts", "models", name)


def save_artifact(name, model, feature_columns, model_config, training_period, metrics_snapshot, version):
    d = artifact_dir(name)
    os.makedirs(d, exist_ok=True)
    joblib.dump(model, os.path.join(d, "model.joblib"))
    meta = {
        "feature_columns": feature_columns,
        "model_config": model_config,
        "training_period": training_period,
        "version": version,
        "metrics_snapshot": metrics_snapshot,
    }
    with open(os.path.join(d, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    return d


def load_artifact(name):
    d = artifact_dir(name)
    model = joblib.load(os.path.join(d, "model.joblib"))
    with open(os.path.join(d, "meta.json")) as f:
        meta = json.load(f)
    return model, meta
