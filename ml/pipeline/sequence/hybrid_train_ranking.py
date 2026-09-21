import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from pipeline import config
from pipeline.sequence.dataset import balanced_indices
from pipeline.sequence.train import pick_device, set_seed, batch_to_device, epoch_lr
from pipeline.sequence.hybrid_train import predict_scores
from pipeline.sequence.ranking import build_day_index, sample_ranking_batch, pairwise_ranking_loss


def fit_ranking(model, train_dataset, valid_dataset, eval_fn, train_ts_sec, ranking_lambda=0.25,
                 negative_ratio=1.0, batch_size=256, max_epochs=15, patience=3, lr=1e-3,
                 weight_decay=0.01, warmup_frac=0.0, use_schedule=True, grad_clip=1.0,
                 ranking_days_per_step=8, ranking_max_per_day=32,
                 num_workers=0, seed=config.RANDOM_SEED, log_fn=print):
    device = pick_device()
    set_seed(seed)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    criterion = torch.nn.BCEWithLogitsLoss()

    targets_arr = np.asarray(train_dataset.targets)
    day_to_idx, eligible_days = build_day_index(train_ts_sec, targets_arr)
    rng = np.random.default_rng(seed)

    best_key = (-1.0, -1.0)
    best_state = None
    epochs_without_improvement = 0
    history = []

    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        current_lr = epoch_lr(epoch, max_epochs, lr, warmup_frac, use_schedule=use_schedule)
        for group in optimizer.param_groups:
            group["lr"] = current_lr

        idx = balanced_indices(train_dataset.targets, negative_ratio, seed + epoch)
        subset = torch.utils.data.Subset(train_dataset, idx)
        loader = DataLoader(subset, batch_size=batch_size, shuffle=True, num_workers=num_workers)

        model.train()
        total_loss = total_bce = total_rank = 0.0
        n_batches = 0
        for step, batch in enumerate(loader):
            batch = batch_to_device(batch, device)
            optimizer.zero_grad()
            logits = model(batch["state"], batch["alarm"], batch["delta"],
                            batch["hour_sin"], batch["hour_cos"], batch["pad_mask"], batch["features"])
            bce_loss = criterion(logits, batch["target"])
            loss = bce_loss
            rank_loss_val = 0.0

            if ranking_lambda > 0:
                rank_idx, day_boundaries = sample_ranking_batch(
                    day_to_idx, eligible_days, targets_arr, ranking_days_per_step,
                    ranking_max_per_day, rng,
                )
                if len(rank_idx) > 0 and day_boundaries:
                    rank_items = [train_dataset[i] for i in rank_idx]
                    rank_batch = torch.utils.data.default_collate(rank_items)
                    rank_batch = batch_to_device(rank_batch, device)
                    rank_logits = model(rank_batch["state"], rank_batch["alarm"], rank_batch["delta"],
                                         rank_batch["hour_sin"], rank_batch["hour_cos"],
                                         rank_batch["pad_mask"], rank_batch["features"])
                    rank_loss = pairwise_ranking_loss(rank_logits, rank_batch["target"], day_boundaries, F.logsigmoid)
                    if rank_loss is not None:
                        loss = loss + ranking_lambda * rank_loss
                        rank_loss_val = rank_loss.item()

            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()
            total_loss += loss.item()
            total_bce += bce_loss.item()
            total_rank += rank_loss_val
            n_batches += 1
            if ranking_lambda > 0 and step % 20 == 0 and device.type == "mps":
                torch.mps.empty_cache()

        valid_scores = predict_scores(model, valid_dataset, device, num_workers=num_workers)
        metrics = eval_fn(valid_dataset.targets, valid_scores)
        elapsed = time.time() - t0
        metrics["train_loss"] = total_loss / max(n_batches, 1)
        metrics["bce_loss"] = total_bce / max(n_batches, 1)
        metrics["rank_loss"] = total_rank / max(n_batches, 1)
        metrics["epoch_seconds"] = elapsed
        metrics["n_train_samples"] = len(idx)
        metrics["lr"] = current_lr
        history.append({"epoch": epoch, **metrics})
        log_fn(f"epoch={epoch} lr={current_lr:.2e} loss={metrics['train_loss']:.4f} "
               f"bce={metrics['bce_loss']:.4f} rank={metrics['rank_loss']:.4f} "
               f"metric={metrics.get('primary_metric')} ap={metrics.get('avg_precision')} time={elapsed:.1f}s")

        current = metrics.get("primary_metric")
        tiebreak = metrics.get("avg_precision") or 0.0
        if current is not None:
            key = (current, tiebreak)
            if key > best_key:
                best_key = key
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                epochs_without_improvement = 0
            else:
                epochs_without_improvement += 1
                if epochs_without_improvement >= patience:
                    log_fn(f"early stopping at epoch {epoch}")
                    break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, history, device
