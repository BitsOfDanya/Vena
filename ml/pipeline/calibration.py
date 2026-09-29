import numpy as np
from scipy.interpolate import PchipInterpolator
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss


def fit_platt(valid_scores, valid_targets):
    lr = LogisticRegression()
    lr.fit(np.asarray(valid_scores).reshape(-1, 1), valid_targets)
    return lr


def fit_isotonic(valid_scores, valid_targets):
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(valid_scores, valid_targets)
    return iso


def apply_platt(model, scores):
    return model.predict_proba(np.asarray(scores).reshape(-1, 1))[:, 1]


def apply_isotonic(model, scores):
    return model.transform(scores)


def fit_smooth_isotonic(scores, targets, bins=40, grid=200, eps=1e-6):
    scores = np.clip(np.asarray(scores, dtype=float), eps, 1 - eps)
    targets = np.asarray(targets, dtype=float)
    groups = np.array_split(np.argsort(scores, kind="stable"), bins)
    logits = np.log(scores / (1 - scores))
    x = np.array([logits[group].mean() for group in groups])
    rate = np.array([targets[group].mean() for group in groups])
    y = np.clip(fit_isotonic(x, rate).transform(x), 0, 1) + np.arange(len(x)) * 1e-6
    keep = np.concatenate([[True], np.diff(x) > 1e-9])
    curve = PchipInterpolator(x[keep], y[keep])
    points = np.linspace(x[keep][0], x[keep][-1], grid)
    raw = np.concatenate([[0.0], 1 / (1 + np.exp(-points)), [1.0]])
    risk = np.clip(np.concatenate([[y[keep][0]], curve(points), [y[keep][-1]]]), 0, 1)
    return raw, np.maximum.accumulate(risk)


def apply_points(points, scores):
    raw, risk = points
    return np.interp(np.asarray(scores, dtype=float), raw, risk)


def expected_calibration_error(y_true, y_prob, n_bins=10):
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    bins = np.linspace(0, 1, n_bins + 1)
    idx = np.clip(np.digitize(y_prob, bins) - 1, 0, n_bins - 1)
    ece = 0.0
    n = len(y_true)
    bin_stats = []
    for b in range(n_bins):
        mask = idx == b
        if mask.sum() == 0:
            continue
        conf = float(y_prob[mask].mean())
        acc = float(y_true[mask].mean())
        weight = mask.sum() / n
        ece += weight * abs(acc - conf)
        bin_stats.append({"bin": b, "n": int(mask.sum()), "confidence": conf, "accuracy": acc})
    return ece, bin_stats


def calibrate_and_evaluate(model, valid_df, test_df, cols, method="isotonic"):
    valid_scores = model.predict_proba(valid_df[cols])
    valid_targets = valid_df["target"].values
    if method == "isotonic":
        calibrator = fit_isotonic(valid_scores, valid_targets)
        apply_fn = apply_isotonic
    else:
        calibrator = fit_platt(valid_scores, valid_targets)
        apply_fn = apply_platt

    test_scores_raw = model.predict_proba(test_df[cols])
    test_targets = test_df["target"].values
    test_scores_cal = np.clip(apply_fn(calibrator, test_scores_raw), 0, 1)

    brier_raw = brier_score_loss(test_targets, np.clip(test_scores_raw, 0, 1))
    brier_cal = brier_score_loss(test_targets, test_scores_cal)
    ece_raw, _ = expected_calibration_error(test_targets, np.clip(test_scores_raw, 0, 1))
    ece_cal, bins_cal = expected_calibration_error(test_targets, test_scores_cal)

    return {
        "method": method,
        "brier_raw": brier_raw,
        "brier_calibrated": brier_cal,
        "ece_raw": ece_raw,
        "ece_calibrated": ece_cal,
        "reliability_bins": bins_cal,
        "calibrator": calibrator,
        "apply_fn": apply_fn,
    }
