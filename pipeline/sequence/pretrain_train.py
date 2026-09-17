import time

import torch
from torch.utils.data import DataLoader

from pipeline import config
from pipeline.sequence.train import pick_device, set_seed, batch_to_device


def fit_pretrain(model, dataset, batch_size=256, max_epochs=5, lr=1e-3, weight_decay=0.01,
                  mask_weight=1.0, next_weight=1.0, grad_clip=1.0, num_workers=0,
                  seed=config.RANDOM_SEED, log_fn=print):
    device = pick_device()
    set_seed(seed)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=-100)

    history = []
    for epoch in range(1, max_epochs + 1):
        t0 = time.time()
        loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers)
        model.train()
        total_loss = total_mask_loss = total_next_loss = 0.0
        n_batches = 0
        for batch in loader:
            batch = batch_to_device(batch, device)
            optimizer.zero_grad()
            loss = torch.zeros((), device=device)
            mask_loss_val = next_loss_val = 0.0
            if mask_weight > 0:
                logits_mask = model.forward_masked(
                    batch["state_masked"], batch["alarm"], batch["delta"],
                    batch["hour_sin"], batch["hour_cos"], batch["pad_mask"],
                )
                v = logits_mask.size(-1)
                mask_loss = criterion(logits_mask.reshape(-1, v), batch["mask_labels"].reshape(-1))
                loss = loss + mask_weight * mask_loss
                mask_loss_val = mask_loss.item()
            if next_weight > 0:
                logits_next = model.forward_next(
                    batch["state_orig"], batch["alarm"], batch["delta"],
                    batch["hour_sin"], batch["hour_cos"], batch["pad_mask"],
                )
                v = logits_next.size(-1)
                next_loss = criterion(logits_next.reshape(-1, v), batch["next_labels"].reshape(-1))
                loss = loss + next_weight * next_loss
                next_loss_val = next_loss.item()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), grad_clip)
            optimizer.step()
            total_loss += loss.item()
            total_mask_loss += mask_loss_val
            total_next_loss += next_loss_val
            n_batches += 1
        elapsed = time.time() - t0
        row = {
            "epoch": epoch, "loss": total_loss / max(n_batches, 1),
            "mask_loss": total_mask_loss / max(n_batches, 1),
            "next_loss": total_next_loss / max(n_batches, 1),
            "epoch_seconds": elapsed, "n_batches": n_batches,
        }
        history.append(row)
        log_fn(f"pretrain epoch={epoch} loss={row['loss']:.4f} mask={row['mask_loss']:.4f} "
               f"next={row['next_loss']:.4f} time={elapsed:.1f}s")
    return model, history, device
