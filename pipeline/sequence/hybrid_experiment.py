import time

import pandas as pd

from pipeline import config, backtest, experiments
from pipeline.sequence import experiment as seq_experiment, gate_eval, train as train_mod
from pipeline.sequence.index import EventIndex
from pipeline.sequence.hybrid_features import compute_normalized_features
from pipeline.sequence.hybrid_dataset import HybridSequenceDataset
from pipeline.sequence.hybrid_model import HybridEventTransformer
from pipeline.sequence import hybrid_train
from pipeline import training

WINNER_CONFIG = dict(lr=1e-3, warmup_frac=0.0, use_schedule=False, weight_decay=0.01,
                      negative_ratio=1.0, batch_size=256, max_epochs=15, patience=3)


def run_device_hybrid(device, horizon_hours, folds=None, max_len=128, d_model=128, nhead=4,
                       num_layers=3, log_fn=print, cooldown_hours=24, with_neighbors=False,
                       seed=None, ctx=None, predictions_out=None):
    folds = folds or config.ROLLING_FOLDS
    sensor_type = config.SENSOR_ALIASES[device]
    seed = config.RANDOM_SEED if seed is None else seed
    feature_cols = training.feature_columns(with_neighbors=with_neighbors)

    t0 = time.time()
    ctx = ctx or experiments.DeviceContext(sensor_type)
    cand = ctx.build(horizon_hours=horizon_hours, with_neighbors=with_neighbors)
    event_index = EventIndex(ctx.events)
    log_fn(f"{device}/{horizon_hours}h: n_events={len(ctx.events)} n_candidates={len(cand)} "
           f"n_positive={int(cand['target'].sum())} n_channels={len(event_index.channel_ranges)} "
           f"load_time={time.time()-t0:.1f}s")

    channel_ids = cand["channel_id"].astype(str).values
    ts_sec = cand["ts"].values.astype("datetime64[s]").astype("int64")
    targets = cand["target"].values

    results = []
    for fold in folds:
        fdf = backtest.assign_fold(cand, fold)
        train_mask = (fdf["fold_split"] == "train").values
        valid_mask = (fdf["fold_split"] == "valid").values
        if valid_mask.sum() == 0 or fdf.loc[valid_mask, "target"].sum() == 0 or train_mask.sum() == 0:
            log_fn(f"{fold['name']}: skipped, insufficient data")
            continue

        x_norm, cols, mean, std = compute_normalized_features(cand, train_mask, feature_cols=feature_cols)

        train_ds = HybridSequenceDataset(event_index, channel_ids[train_mask], ts_sec[train_mask],
                                          targets[train_mask], x_norm[train_mask], max_len)
        valid_ds = HybridSequenceDataset(event_index, channel_ids[valid_mask], ts_sec[valid_mask],
                                          targets[valid_mask], x_norm[valid_mask], max_len)
        valid_ts = cand.loc[valid_mask, "ts"].values
        eval_fn = seq_experiment.build_eval_fn(valid_ts)

        train_mod.set_seed(seed)
        model = HybridEventTransformer(vocab_size=event_index.vocab_size, feature_dim=len(cols),
                                        d_model=d_model, nhead=nhead, num_layers=num_layers)
        log_fn(f"{fold['name']}: training start, n_train={train_mask.sum()} n_valid={valid_mask.sum()} "
               f"params={model.num_parameters()}")

        t_fold = time.time()
        model, history, device_used = hybrid_train.fit(
            model, train_ds, valid_ds, eval_fn, log_fn=log_fn, seed=seed,
            **WINNER_CONFIG,
        )
        valid_scores = hybrid_train.predict_scores(model, valid_ds, device_used)
        cand_valid = cand.loc[valid_mask]
        if predictions_out is not None:
            predictions_out[fold["name"]] = pd.DataFrame({
                "channel_id": cand_valid["channel_id"].values,
                "ts": cand_valid["ts"].values,
                "target": cand_valid["target"].values,
                "score": valid_scores,
            })
        metrics = gate_eval.full_metrics(cand_valid, valid_scores, ctx.episodes, horizon_hours,
                                          cooldown_hours=cooldown_hours)
        metrics["fold"] = fold["name"]
        metrics["n_train"] = int(train_mask.sum())
        metrics["n_valid"] = int(valid_mask.sum())
        metrics["n_epochs_run"] = len(history)
        metrics["fold_seconds"] = time.time() - t_fold
        metrics["source"] = "hybrid_neighbors" if with_neighbors else "hybrid"
        metrics["device"] = device
        metrics["horizon_hours"] = horizon_hours
        metrics["seed"] = seed
        results.append(metrics)
        log_fn(f"{fold['name']}: done in {metrics['fold_seconds']:.1f}s, "
               f"avg_precision={metrics.get('avg_precision')}, "
               f"daily_top1={metrics.get('daily_precision_top_1pct')}, "
               f"alert_precision={metrics.get('alert_precision')}, "
               f"episode_recall={metrics.get('episode_recall')}")

    return pd.DataFrame(results)
