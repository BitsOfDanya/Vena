import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from pipeline import config
from pipeline.sequence.dataset import balanced_indices
from pipeline.sequence.train import pick_device, set_seed, batch_to_device, epoch_lr
from pipeline.sequence.hybrid_train import predict_scores


def fit_distill(model, train_dataset, valid_dataset, eval_fn, distill_lambda=0.0, negative_ratio=1.0,
                 batch_size=256, max_epochs=15, patience=3, lr=1e-3, weight_decay=0.01,
                 warmup_frac=0.0, use_schedule=True, grad_clip=1.0, num_workers=0,
                 seed=config.RANDOM_SEED, log_fn=print):
    device = pick_device()
    set_seed(seed)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

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
        total_loss = 0.0
        total_bce = 0.0
        total_distill = 0.0
        n_batches = 0
        for batch in loader:
            batch = batch_to_device(batch, device)
            optimizer.zero_grad()
            logits = model(batch["state"], batch["alarm"], batch["delta"],
                            batch["hour_sin"], batch["hour_cos"], batch["pad_mask"], batch["features"])
            bce = F.binary_cross_entropy_with_logits(logits, batch["target"])
            distill = F.binary_cross_entropy_with_logits(logits, batch["teacher"])
            loss = bce + distill_lambda * distill
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()
            total_loss += loss.item()
            total_bce += bce.item()
            total_distill += distill.item()
            n_batches += 1

        valid_scores = predict_scores(model, valid_dataset, device, num_workers=num_workers)
        metrics = eval_fn(valid_dataset.targets, valid_scores)
        elapsed = time.time() - t0
        metrics["train_loss"] = total_loss / max(n_batches, 1)
        metrics["train_bce"] = total_bce / max(n_batches, 1)
        metrics["train_distill"] = total_distill / max(n_batches, 1)
        metrics["epoch_seconds"] = elapsed
        metrics["n_train_samples"] = len(idx)
        metrics["lr"] = current_lr
        history.append({"epoch": epoch, **metrics})
        log_fn(f"epoch={epoch} lr={current_lr:.2e} loss={metrics['train_loss']:.4f} "
               f"bce={metrics['train_bce']:.4f} distill={metrics['train_distill']:.4f} "
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
