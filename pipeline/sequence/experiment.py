import time

import numpy as np
import pandas as pd

from pipeline import config, extract, episodes as episodes_mod, candidates as candidates_mod, backtest
from pipeline import evaluate as evaluate_mod
from pipeline.sequence.index import EventIndex
from pipeline.sequence.dataset import EventSequenceDataset
from pipeline.sequence.model import EventTransformer
from pipeline.sequence import train as train_mod
from pipeline.sequence import gate_eval

DEVICE_SENSOR_TYPES = {
    "pump": config.SENSOR_ALIASES["pump"],
    "fan": config.SENSOR_ALIASES["fan"],
    "smoke": config.SENSOR_ALIASES["smoke"],
}


def build_eval_fn(valid_ts=None):
    def eval_fn(y_true, y_score):
        m = evaluate_mod.evaluate(y_true, y_score)
        if valid_ts is not None:
            d = evaluate_mod.evaluate_daily_topk(valid_ts, y_true, y_score, k_fracs=[0.01])
            m.update(d)
            m["primary_metric"] = m.get("daily_precision_top_1pct")
        else:
            m["primary_metric"] = m.get("avg_precision")
        return m
    return eval_fn


def load_device_data(sensor_type, horizon_hours):
    events = extract.extract_events(sensor_type)
    episodes = episodes_mod.build_episodes(events)
    cand = candidates_mod.generate_candidates(events, sensor_type)
    cand = episodes_mod.assign_targets(cand, episodes, horizon_hours)
    return events, episodes, cand


def load_device_context(device, horizon_hours):
    sensor_type = DEVICE_SENSOR_TYPES[device]
    events, episodes, cand = load_device_data(sensor_type, horizon_hours)
    event_index = EventIndex(events)
    return events, episodes, cand, event_index


def print_compute_estimate(n_train, n_valid, max_len, model, batch_size, negative_ratio, lr, warmup_frac, weight_decay):
    print("=== compute estimate ===")
    print(f"train candidates (full): {n_train}")
    print(f"valid candidates: {n_valid}")
    print(f"max sequence length: {max_len}")
    print(f"model parameters: {model.num_parameters():,}")
    print(f"batch_size: {batch_size}, negative_ratio: {negative_ratio}")
    print(f"lr: {lr}, warmup_frac: {warmup_frac}, weight_decay: {weight_decay}")


def run_fold_config(cand, event_index, episodes, fold, horizon_hours, max_len=128, d_model=128, nhead=4,
                     num_layers=3, lr=1e-3, warmup_frac=0.0, use_schedule=True, weight_decay=0.01,
                     negative_ratio=1.0, use_balanced_sampling=True, pos_weight_mode=None, batch_size=256,
                     max_epochs=15, patience=3, log_fn=print, compute_gate_metrics=True, cooldown_hours=24,
                     seed=None):
    seed = seed if seed is not None else config.RANDOM_SEED
    channel_ids = cand["channel_id"].astype(str).values
    ts_sec = cand["ts"].values.astype("datetime64[s]").astype(np.int64)
    targets = cand["target"].values

    fdf = backtest.assign_fold(cand, fold)
    train_mask = (fdf["fold_split"] == "train").values
    valid_mask = (fdf["fold_split"] == "valid").values
    if valid_mask.sum() == 0 or fdf.loc[valid_mask, "target"].sum() == 0 or train_mask.sum() == 0:
        log_fn(f"{fold['name']}: skipped, insufficient data")
        return None

    train_ds = EventSequenceDataset(event_index, channel_ids[train_mask], ts_sec[train_mask],
                                     targets[train_mask], max_len)
    valid_ds = EventSequenceDataset(event_index, channel_ids[valid_mask], ts_sec[valid_mask],
                                     targets[valid_mask], max_len)
    valid_ts = cand.loc[valid_mask, "ts"].values
    eval_fn = build_eval_fn(valid_ts)

    pos_weight = None
    if not use_balanced_sampling and pos_weight_mode == "auto":
        n_pos = targets[train_mask].sum()
        n_neg = train_mask.sum() - n_pos
        pos_weight = float(n_neg / max(n_pos, 1))

    train_mod.set_seed(seed)
    model = EventTransformer(vocab_size=event_index.vocab_size, d_model=d_model, nhead=nhead, num_layers=num_layers)
    print_compute_estimate(train_mask.sum(), valid_mask.sum(), max_len, model, batch_size, negative_ratio,
                            lr, warmup_frac, weight_decay)

    log_fn(f"{fold['name']}: training start, n_train={train_mask.sum()} n_valid={valid_mask.sum()}")
    t0 = time.time()
    model, history, device = train_mod.fit(
        model, train_ds, valid_ds, eval_fn,
        negative_ratio=negative_ratio, batch_size=batch_size, max_epochs=max_epochs, patience=patience,
        lr=lr, weight_decay=weight_decay, warmup_frac=warmup_frac, use_schedule=use_schedule,
        use_balanced_sampling=use_balanced_sampling, pos_weight=pos_weight,
        log_fn=log_fn, seed=seed,
    )
    valid_scores = train_mod.predict_scores(model, valid_ds, device)

    if compute_gate_metrics:
        cand_valid = cand.loc[valid_mask]
        metrics = gate_eval.full_metrics(cand_valid, valid_scores, episodes, horizon_hours, cooldown_hours=cooldown_hours)
    else:
        metrics = evaluate_mod.evaluate(targets[valid_mask], valid_scores)
        metrics.update(evaluate_mod.evaluate_daily_topk(valid_ts, targets[valid_mask], valid_scores))

    metrics["fold"] = fold["name"]
    metrics["n_train"] = int(train_mask.sum())
    metrics["n_valid"] = int(valid_mask.sum())
    metrics["n_epochs_run"] = len(history)
    metrics["fold_seconds"] = time.time() - t0
    metrics["lr"] = lr
    metrics["warmup_frac"] = warmup_frac
    metrics["use_schedule"] = use_schedule
    metrics["weight_decay"] = weight_decay
    metrics["negative_ratio"] = negative_ratio
    metrics["use_balanced_sampling"] = use_balanced_sampling
    log_fn(f"{fold['name']}: done in {metrics['fold_seconds']:.1f}s, "
           f"avg_precision={metrics.get('avg_precision')}, "
           f"daily_top1={metrics.get('daily_precision_top_1pct')}")
    return metrics, history


def run_grid_single_fold(device, horizon_hours, fold, configs, max_len=128, d_model=128, nhead=4, num_layers=3,
                          batch_size=256, max_epochs=8, patience=2, log_fn=print):
    events, episodes, cand, event_index = load_device_context(device, horizon_hours)
    log_fn(f"n_events={len(events)} n_candidates={len(cand)} n_positive={int(cand['target'].sum())}")
    log_fn(f"vocab_size={event_index.vocab_size} n_channels={len(event_index.channel_ranges)}")

    results = []
    for i, cfg in enumerate(configs):
        log_fn(f"=== grid config {i+1}/{len(configs)}: {cfg} ===")
        out = run_fold_config(
            cand, event_index, episodes, fold, horizon_hours, max_len=max_len, d_model=d_model,
            nhead=nhead, num_layers=num_layers, batch_size=batch_size, max_epochs=max_epochs,
            patience=patience, compute_gate_metrics=False, log_fn=log_fn, **cfg,
        )
        if out is None:
            continue
        metrics, history = out
        metrics["config_id"] = i
        results.append(metrics)
    return pd.DataFrame(results)


def run_all_folds_config(device, horizon_hours, cfg, folds=None, max_len=128, d_model=128, nhead=4, num_layers=3,
                          batch_size=256, max_epochs=15, patience=3, log_fn=print, compute_gate_metrics=True):
    folds = folds or config.ROLLING_FOLDS
    events, episodes, cand, event_index = load_device_context(device, horizon_hours)
    log_fn(f"n_events={len(events)} n_candidates={len(cand)} n_positive={int(cand['target'].sum())}")
    log_fn(f"vocab_size={event_index.vocab_size} n_channels={len(event_index.channel_ranges)}")

    results = []
    for fold in folds:
        out = run_fold_config(
            cand, event_index, episodes, fold, horizon_hours, max_len=max_len, d_model=d_model,
            nhead=nhead, num_layers=num_layers, batch_size=batch_size, max_epochs=max_epochs,
            patience=patience, compute_gate_metrics=compute_gate_metrics, log_fn=log_fn, **cfg,
        )
        if out is None:
            continue
        metrics, history = out
        results.append(metrics)
    return pd.DataFrame(results)
