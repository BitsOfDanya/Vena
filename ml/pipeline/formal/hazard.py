import numpy as np

from pipeline import models as models_mod

BIN_EDGES = (0.0, 6.0, 12.0, 24.0, 48.0, 72.0)
N_BINS = len(BIN_EDGES) - 1


def event_bin(ttf):
    ttf = np.asarray(ttf, dtype=np.float64)
    out = np.full(len(ttf), -1, dtype=np.int64)
    valid = ~np.isnan(ttf) & (ttf <= BIN_EDGES[-1])
    out[valid] = np.searchsorted(np.array(BIN_EDGES[1:]), ttf[valid], side="left")
    return out


def expand_person_period(features, ttf):
    bins = event_bin(ttf)
    last = np.where(bins >= 0, bins, N_BINS - 1)
    counts = last + 1
    row_idx = np.repeat(np.arange(len(bins)), counts)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    bin_of_row = np.arange(counts.sum()) - np.repeat(starts, counts)
    label = ((bins[row_idx] == bin_of_row) & (bins[row_idx] >= 0)).astype(np.int8)
    return row_idx, bin_of_row, label


def cumulative_probability(hazards, upto_bin):
    return 1.0 - np.prod(1.0 - hazards[:, : upto_bin + 1], axis=1)


def _with_bin(x, bin_of_row):
    out = x.copy()
    out["hz_bin"] = bin_of_row.astype(np.float32)
    for b in range(N_BINS):
        out[f"hz_bin_{b}"] = (bin_of_row == b).astype(np.float32)
    return out


def hazard_fit_score(model_name, cols, ttf_col="ttf_hours"):
    def fn(frame, train, score_mask, fold):
        x_train = frame.loc[train, cols].reset_index(drop=True)
        row_idx, bin_of_row, label = expand_person_period(x_train, frame.loc[train, ttf_col].values)
        xe = _with_bin(x_train.iloc[row_idx].reset_index(drop=True), bin_of_row)
        model = models_mod.MODEL_REGISTRY[model_name]()
        model.fit(xe, label)
        x_score = frame.loc[score_mask, cols].reset_index(drop=True)
        n = len(x_score)
        hazards = np.zeros((n, N_BINS))
        for b in range(N_BINS):
            hazards[:, b] = model.predict_proba(_with_bin(x_score, np.full(n, b)))
        fn.last_hazards = hazards
        return cumulative_probability(hazards, N_BINS - 1)
    return fn
