"""Research-only score blending for equipment-health models."""

import numpy as np


class ProbabilityBlend:  # pylint: disable=too-few-public-methods
    """Expose the repository's one-dimensional positive-score interface."""

    def __init__(self, linear_model, tree_model, linear_weight=0.5):
        if not 0.0 <= linear_weight <= 1.0:
            raise ValueError("linear_weight must be between 0 and 1")
        self.linear_model = linear_model
        self.tree_model = tree_model
        self.linear_weight = float(linear_weight)

    def predict_proba(self, features):
        """Return the weighted positive-class score for each feature row."""
        linear = np.asarray(self.linear_model.predict_proba(features), dtype=float)
        tree = np.asarray(self.tree_model.predict_proba(features), dtype=float)
        if linear.shape != tree.shape:
            raise ValueError("component models returned different score shapes")
        return self.linear_weight * linear + (1.0 - self.linear_weight) * tree
