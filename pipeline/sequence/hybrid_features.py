import numpy as np

from pipeline import training


def compute_normalized_features(featured_cand, train_mask, feature_cols=None):
    """featured_cand must already carry engineered feature columns, e.g. the output of
    pipeline.experiments.DeviceContext.build() (features_base joined once at context
    construction) — do not pass a bare candidate frame through pipeline.features.compute_features
    a second time, its join would collide with columns already present."""
    feature_cols = feature_cols or training.feature_columns()
    x = featured_cand[feature_cols].fillna(-1).values.astype(np.float32)
    mean = x[train_mask].mean(axis=0)
    std = x[train_mask].std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    x_norm = (x - mean) / std
    return x_norm, feature_cols, mean, std
