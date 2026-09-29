import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from experiments.run_blend_experiment import fit_models
from experiments.run_recency_experiment import cache_paths
from pipeline import training
from pipeline.ensemble import ProbabilityBlend

OUTPUT = Path("artifacts/experimental/pump72_blend_20260924")
MANIFEST = Path("experiments/dataset_manifest.sha256")
VALIDATION = Path("experiments/pump_blend_validation_2025.jsonl")


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    cache, _, _ = cache_paths("pump", False)
    frame = pd.read_parquet(cache)
    linear, tree = fit_models(frame, 2026)
    model = ProbabilityBlend(linear, tree, linear_weight=0.5)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    model_path = OUTPUT / "model.joblib"
    joblib.dump(model, model_path)

    cols = training.feature_columns()
    sample = frame.loc[frame["ts"].dt.year == 2024, cols].head(100)
    loaded = joblib.load(model_path)
    if not np.allclose(model.predict_proba(sample), loaded.predict_proba(sample)):
        raise RuntimeError("serialized model changed predictions")

    with VALIDATION.open(encoding="utf-8") as source:
        prior = next(
            item for item in map(json.loads, source)
            if item["linear_weight"] == 0.5
        )
    metadata = {
        "status": "research_only",
        "sensor_type": "Состояние насоса",
        "target": "onset of Неисправен within 72 hours",
        "horizon_hours": 72,
        "train_years": "2023-2025",
        "embargo_hours_before_2026": 168,
        "linear_weight": 0.5,
        "tree_params": {"num_leaves": 7, "min_child_samples": 500},
        "feature_columns": cols,
        "frozen_p70_threshold_from_2025": prior["threshold_p70"],
        "calibrated": False,
        "dataset_manifest_sha256": sha256_file(MANIFEST),
        "model_sha256": sha256_file(model_path),
    }
    (OUTPUT / "meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    print(json.dumps({"artifact": str(OUTPUT), "model_sha256": metadata["model_sha256"]}))


if __name__ == "__main__":
    main()
