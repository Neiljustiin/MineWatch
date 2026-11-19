"""
Training loop PRODUKSI untuk FC-Siam-diff -- beda dari train.py (smoke test).

Yang ditambahin dibanding smoke test (train.py):
  1. Mixed precision (AMP) -- RTX 3060 (Ampere) punya tensor core, FP32 penuh
     nyia-nyiain potensi speedup. autocast + GradScaler kasih speedup ~1.5-2x
     nyaris gratis dengan risiko numerik minimal (praktik standar).
  2. pin_memory=True -- transfer CPU->GPU lebih cepat.
  3. num_workers dinaikin (default 4, dari 2 di smoke test) -- pas smoke test
     subset 3000 patch, RAM cuma kepake 64MB/12GB (swap 0%), jauh di bawah
     yang dikhawatirkan sebelumnya. Ada headroom buat worker lebih banyak.
  4. Train/val split proper -- smoke test cuma loop di train split doang,
     nggak pernah dicek val loss.
  5. Checkpointing model TERBAIK (berdasar val loss, bukan train loss) --
     model yang overfit ke train tapi jelek di val HARUS ketauan, bukan
     keikut ke-save begitu aja.
  6. Early stopping -- stop otomatis kalau val loss nggak membaik dalam
     `patience` epoch berturut-turut. Nggak ngandelin tebakan "butuh N epoch".
  7. LR scheduler (ReduceLROnPlateau) -- turunin learning rate otomatis
     kalau val loss stuck, standar buat ngehindarin training mentok.

CARA PAKAI:
    python3 train_production.py --base-ch 32 --epochs 50 --batch-size 8

base_ch=32 dipilih sebagai default (16 Nov 2026, konsultasi resource):
kapasitas lebih wajar dari smoke-test (16) tapi lebih aman buat VRAM 12GB
& waktu training dibanding base_ch=64 yang belum pernah divalidasi.
"""
import argparse
import json
import os
import sys
import time

import torch
from torch.amp import GradScaler, autocast
from torch.utils.data import DataLoader, WeightedRandomSampler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset_loader import TorchMineNetCD  # noqa: E402
from model import FCSiamDiff, FocalDiceLoss, FocalLoss  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
CHECKPOINT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "checkpoints")


def make_loader(split, subset_size, batch_size, num_workers, shuffle_with_sampler):
    ds = TorchMineNetCD(split, subset_size=subset_size)
    if shuffle_with_sampler:
        # Weighted sampler: oversample patch 'ada perubahan' (~18-28% dari total,
        # lihat DATASET_MANIFEST.md -- class imbalance di level patch)
        # Ambil flag langsung dari base dataset (tanpa lewat __getitem__ TorchMineNetCD)
        # -> nggak kena augmentasi/normalisasi, jauh lebih murah buat ~48k patch.
        has_change_flags = [bool(ds.base[j]["has_change"]) for j in ds.indices]
        n_pos = sum(has_change_flags)
        print(f"[{split}] {n_pos}/{len(ds)} patch ada perubahan ({n_pos/len(ds)*100:.1f}%)")
        weights = [3.0 if hc else 1.0 for hc in has_change_flags]
        sampler = WeightedRandomSampler(weights, num_samples=len(ds), replacement=True)
        loader = DataLoader(
            ds, batch_size=batch_size, sampler=sampler,
            num_workers=num_workers, pin_memory=(DEVICE.type == "cuda"),
            collate_fn=_collate,
        )
    else:
        loader = DataLoader(
            ds, batch_size=batch_size, shuffle=False,
            num_workers=num_workers, pin_memory=(DEVICE.type == "cuda"),
            collate_fn=_collate,
        )
    return loader, len(ds)


def _collate(batch):
    return (
        torch.stack([b[0] for b in batch]),
        torch.stack([b[1] for b in batch]),
        torch.stack([b[2] for b in batch]),
    )


def run_epoch(model, loader, criterion, optimizer, scaler, train: bool, ema_model=None):
    model.train(train)
    total_loss = 0.0
    n_batches = 0
    for img_a, img_b, label in loader:
        img_a = img_a.to(DEVICE, non_blocking=True)
        img_b = img_b.to(DEVICE, non_blocking=True)
        label = label.to(DEVICE, non_blocking=True)

        if train:
            optimizer.zero_grad(set_to_none=True)

        with torch.set_grad_enabled(train):
            with autocast(device_type=DEVICE.type, enabled=(DEVICE.type == "cuda")):
                logits = model(img_a, img_b)
                loss = criterion(logits, label)

            if torch.isnan(loss):
                raise RuntimeError("Loss jadi NaN -- training production DIHENTIKAN, perlu dicek.")

            if train:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
                if ema_model is not None:
                    ema_model.update_parameters(model)

        total_loss += loss.item()
        n_batches += 1

    return total_loss / max(n_batches, 1)


def train_production(
    base_ch=32,
    epochs=50,
    batch_size=8,
    lr=3e-4,
    weight_decay=1e-4,
    num_workers=4,
    patience=12,
    train_subset=None,
    val_subset=None,
    run_name=None,
    dropout=0.3,
    loss_name="focal_dice",
    scheduler_name="cosine",
    warmup_epochs=2,
    ema_decay=0.999,
):
    """
    Regularisasi anti-overfitting (ditambah 16 Nov 2026 setelah v1/v2 overfit
    mulai epoch ~14; default baru di bawah ini = konfigurasi v3):
      - dropout      : Dropout2d di bottleneck/decoder (model.py). 0 = off (v1/v2).
      - loss_name    : "focal" (v1/v2) atau "focal_dice" (Dice ngarahin ke IoU).
      - scheduler    : "plateau" (v1/v2) atau "cosine" (warmup linear lalu cosine
                       decay ke ~0 di epoch terakhir -- lebih halus di akhir).
      - lr           : default turun 1e-3 -> 3e-4 (v1/v2 best epoch cuma 12-14,
                       indikasi LR terlalu agresif).
      - ema_decay    : EMA bobot model (0 = off). Val & checkpoint pakai bobot EMA,
                       bukan bobot mentah -- lebih stabil, biasanya +IoU kecil.
      - patience     : 8 -> 12, karena kurva val lebih landai dengan LR rendah.
    """
    run_name = run_name or f"fcsiamdiff_base{base_ch}_{int(time.time())}"
    ckpt_dir = os.path.join(CHECKPOINT_DIR, run_name)
    os.makedirs(ckpt_dir, exist_ok=True)

    config = {k: v for k, v in locals().items() if k not in ("ckpt_dir",)}
    print(f"=== Training produksi FC-Siam-diff | base_ch={base_ch} | device={DEVICE} ===")
    if DEVICE.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"AMP (mixed precision): {'aktif' if DEVICE.type == 'cuda' else 'nonaktif (CPU)'}")
    print(f"Checkpoint dir: {ckpt_dir}")
    print(f"Config: {json.dumps(config)}")
    with open(os.path.join(ckpt_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)

    train_loader, n_train = make_loader("train", train_subset, batch_size, num_workers, shuffle_with_sampler=True)
    val_loader, n_val = make_loader("val", val_subset, batch_size, num_workers, shuffle_with_sampler=False)
    print(f"Train: {n_train} patch | Val: {n_val} patch")

    model = FCSiamDiff(base_ch=base_ch, dropout=dropout).to(DEVICE)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Model params: {n_params:,}")

    if loss_name == "focal_dice":
        criterion = FocalDiceLoss(alpha=0.75, gamma=2.0, dice_weight=0.5)
    elif loss_name == "focal":
        criterion = FocalLoss(alpha=0.75, gamma=2.0)
    else:
        raise ValueError(f"loss tidak dikenal: {loss_name}")
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)

    if scheduler_name == "cosine":
        # Warmup linear 0->lr selama warmup_epochs, lalu cosine turun ke ~0 di epoch terakhir.
        # Di-step PER EPOCH (bukan per batch) biar sederhana & log-nya gampang dibaca.
        import math

        def _lr_lambda(ep):
            if ep < warmup_epochs:
                return (ep + 1) / warmup_epochs
            progress = (ep - warmup_epochs) / max(1, epochs - warmup_epochs)
            return 0.5 * (1.0 + math.cos(math.pi * min(1.0, progress)))

        scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, _lr_lambda)
    elif scheduler_name == "plateau":
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=3)
    else:
        raise ValueError(f"scheduler tidak dikenal: {scheduler_name}")
    scaler = GradScaler(device=DEVICE.type, enabled=(DEVICE.type == "cuda"))

    # EMA: rata-rata eksponensial bobot (termasuk buffer BatchNorm via use_buffers=True).
    # Decay di-ramp dari 0 -> ema_decay seiring jumlah step (gaya timm), supaya epoch awal
    # EMA nggak "ketinggalan" di bobot random (penting kalau step/epoch sedikit).
    ema_model = None
    if ema_decay and ema_decay > 0:
        from torch.optim.swa_utils import AveragedModel

        def _ema_avg(avg_p, cur_p, num_averaged):
            n = float(num_averaged)
            d = min(ema_decay, (1.0 + n) / (10.0 + n))
            return avg_p * d + cur_p * (1.0 - d)

        ema_model = AveragedModel(model, avg_fn=_ema_avg, use_buffers=True)

    best_val_loss = float("inf")
    epochs_no_improve = 0
    history = []

    for epoch in range(1, epochs + 1):
        t0 = time.time()
        train_loss = run_epoch(model, train_loader, criterion, optimizer, scaler, train=True, ema_model=ema_model)
        eval_model = ema_model if ema_model is not None else model
        val_loss = run_epoch(eval_model, val_loader, criterion, optimizer, scaler, train=False)
        if scheduler_name == "plateau":
            scheduler.step(val_loss)
        else:
            scheduler.step()
        elapsed = time.time() - t0

        improved = val_loss < best_val_loss
        if improved:
            best_val_loss = val_loss
            epochs_no_improve = 0
            state = (ema_model.module if ema_model is not None else model).state_dict()
            torch.save({
                "epoch": epoch, "model_state": state,
                "val_loss": val_loss, "base_ch": base_ch, "dropout": dropout,
                "config": config, "weights": "ema" if ema_model is not None else "raw",
            }, os.path.join(ckpt_dir, "best_model.pt"))
        else:
            epochs_no_improve += 1

        current_lr = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch}/{epochs} | train_loss={train_loss:.4f} | val_loss={val_loss:.4f} "
            f"{'(BEST, saved)' if improved else f'(no improve {epochs_no_improve}/{patience})'} "
            f"| lr={current_lr:.2e} | {elapsed:.1f}s/epoch"
        )
        history.append({
            "epoch": epoch, "train_loss": train_loss, "val_loss": val_loss,
            "lr": current_lr, "elapsed_s": elapsed, "improved": improved,
        })
        with open(os.path.join(ckpt_dir, "history.json"), "w") as f:
            json.dump(history, f, indent=2)

        if epochs_no_improve >= patience:
            print(f"\nEarly stopping -- val_loss nggak membaik dalam {patience} epoch berturut-turut.")
            break

    print(f"\nSelesai. Best val_loss={best_val_loss:.4f}, checkpoint di {ckpt_dir}/best_model.pt")
    return history


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ch", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4, help="AdamW weight decay (L2 regularisasi, lawan overfitting)")
    parser.add_argument("--num-workers", type=int, default=4)
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--dropout", type=float, default=0.3, help="Dropout2d di bottleneck/decoder; 0 = off (v1/v2)")
    parser.add_argument("--loss", choices=["focal", "focal_dice"], default="focal_dice")
    parser.add_argument("--scheduler", choices=["plateau", "cosine"], default="cosine")
    parser.add_argument("--warmup-epochs", type=int, default=2)
    parser.add_argument("--ema-decay", type=float, default=0.999, help="EMA bobot; 0 = off")
    parser.add_argument("--train-subset", type=int, default=None, help="buat uji cepat, batasi jumlah patch train")
    parser.add_argument("--val-subset", type=int, default=None, help="buat uji cepat, batasi jumlah patch val")
    parser.add_argument("--run-name", type=str, default=None)
    args = parser.parse_args()

    train_production(
        base_ch=args.base_ch, epochs=args.epochs, batch_size=args.batch_size,
        lr=args.lr, weight_decay=args.weight_decay, num_workers=args.num_workers, patience=args.patience,
        train_subset=args.train_subset, val_subset=args.val_subset, run_name=args.run_name,
        dropout=args.dropout, loss_name=args.loss, scheduler_name=args.scheduler,
        warmup_epochs=args.warmup_epochs, ema_decay=args.ema_decay,
    )
