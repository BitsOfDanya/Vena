import time

import numpy as np
import torch
from torch.utils.data import DataLoader

from pipeline import config
from pipeline.sequence import model as model_mod
from pipeline.sequence.dataset import balanced_indices


def pick_device():
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def set_seed(seed=config.RANDOM_SEED):
    torch.manual_seed(seed)
    np.random.seed(seed)


def batch_to_device(batch, device):
    return {k: v.to(device) for k, v in batch.items()}


def epoch_lr(epoch, max_epochs, base_lr, warmup_frac, use_schedule=True):
    if not use_schedule:
        return base_lr
    if warmup_frac <= 0:
        warmup_epochs = 0
    else:
        warmup_epochs = max(1, round(warmup_frac * max_epochs))
    if epoch <= warmup_epochs:
        return base_lr * epoch / warmup_epochs
    remaining = max(1, max_epochs - warmup_epochs)
    progress = min((epoch - warmup_epochs) / remaining, 1.0)
    return base_lr * 0.5 * (1 + np.cos(np.pi * progress))


@torch.no_grad()
def predict_scores(model, dataset, device, batch_size=512, num_workers=0):
    model.eval()
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    scores = []
    for batch in loader:
        batch = batch_to_device(batch, device)
        logits = model(batch["state"], batch["alarm"], batch["delta"],
                        batch["hour_sin"], batch["hour_cos"], batch["pad_mask"])
        scores.append(torch.sigmoid(logits).cpu().numpy())
    return np.concatenate(scores)


def fit(model, train_dataset, valid_dataset, eval_fn, negative_ratio=1.0, batch_size=256,
        max_epochs=15, patience=3, lr=1e-3, weight_decay=0.01, warmup_frac=0.0, use_schedule=True,
        use_balanced_sampling=True, pos_weight=None, grad_clip=1.0,
        num_workers=0, seed=config.RANDOM_SEED, log_fn=print):
    device = pick_device()
    set_seed(seed)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    pw = torch.tensor(pos_weight, device=device) if pos_weight else None
    criterion = torch.nn.BCEWithLogitsLoss(pos_weight=pw)

    best_key = (-1.0, -1.0)
    best_state = None
    epochs_without_improvement = 0
    history = []

    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        current_lr = epoch_lr(epoch, max_epochs, lr, warmup_frac, use_schedule=use_schedule)
        for group in optimizer.param_groups:
            group["lr"] = current_lr

        if use_balanced_sampling:
            idx = balanced_indices(train_dataset.targets, negative_ratio, seed + epoch)
        else:
            idx = np.arange(len(train_dataset.targets))
        subset = torch.utils.data.Subset(train_dataset, idx)
        loader = DataLoader(subset, batch_size=batch_size, shuffle=True, num_workers=num_workers)

        model.train()
        total_loss = 0.0
        n_batches = 0
        for batch in loader:
            batch = batch_to_device(batch, device)
            optimizer.zero_grad()
            logits = model(batch["state"], batch["alarm"], batch["delta"],
                            batch["hour_sin"], batch["hour_cos"], batch["pad_mask"])
            loss = criterion(logits, batch["target"])
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()
            total_loss += loss.item()
            n_batches += 1

        valid_scores = predict_scores(model, valid_dataset, device, num_workers=num_workers)
        metrics = eval_fn(valid_dataset.targets, valid_scores)
        elapsed = time.time() - t0
        metrics["train_loss"] = total_loss / max(n_batches, 1)
        metrics["epoch_seconds"] = elapsed
        metrics["n_train_samples"] = len(idx)
        metrics["lr"] = current_lr
        history.append({"epoch": epoch, **metrics})
        log_fn(f"epoch={epoch} lr={current_lr:.2e} loss={metrics['train_loss']:.4f} "
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
