"""
Training loop untuk FC-Siam-diff, pakai TorchMineNetCD dari dataset_loader.py
(dibungkus di atas loader `dataset_loader.MineNetCDPatches`).

SMOKE TEST (bukan full training production):
- Subset data kecil (default 300 patch train) biar jalan cepat
- Beberapa puluh training step, cukup buat buktiin loss bisa turun & kode
  tidak crash/NaN -- bukan buat dapetin model yang bagus
- Jalan otomatis pakai GPU (RTX 3060, lab server) kalau kedetect, fallback CPU
- Full training production (ribuan step, dataset penuh, banyak epoch) baru
  dijalanin setelah smoke test ini lolos
"""
import sys
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, WeightedRandomSampler

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from dataset_loader import TorchMineNetCD  # noqa: E402
from model import FCSiamDiff, FocalLoss  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def smoke_test(subset_size=300, batch_size=4, n_steps=50, log_every=10):
    print(f"=== Smoke test training loop FC-Siam-diff (device={DEVICE}) ===")
    if DEVICE.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
    t0 = time.time()

    ds = TorchMineNetCD("train", subset_size=subset_size)
    print(f"Subset: {len(ds)} patch (random sample dari train split)")

    # Weighted sampler: oversample patch 'ada perubahan' karena cuma ~20% dari total
    # (lihat DATASET_MANIFEST.md -- class imbalance di level patch)
    has_change_flags = [ds[i][3] for i in range(len(ds))]
    n_pos = sum(has_change_flags)
    print(f"Distribusi subset: {n_pos}/{len(ds)} patch ada perubahan ({n_pos/len(ds)*100:.1f}%)")
    weights = [3.0 if hc else 1.0 for hc in has_change_flags]  # oversample positif ~3x
    sampler = WeightedRandomSampler(weights, num_samples=len(ds), replacement=True)

    loader = DataLoader(ds, batch_size=batch_size, sampler=sampler, num_workers=2,
                         collate_fn=lambda batch: (
                             torch.stack([b[0] for b in batch]),
                             torch.stack([b[1] for b in batch]),
                             torch.stack([b[2] for b in batch]),
                         ))

    model = FCSiamDiff(base_ch=16).to(DEVICE)
    criterion = FocalLoss(alpha=0.75, gamma=2.0)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    model.train()
    losses = []
    step = 0
    data_iter = iter(loader)
    while step < n_steps:
        try:
            img_a, img_b, label = next(data_iter)
        except StopIteration:
            data_iter = iter(loader)
            img_a, img_b, label = next(data_iter)

        img_a, img_b, label = img_a.to(DEVICE), img_b.to(DEVICE), label.to(DEVICE)

        optimizer.zero_grad()
        logits = model(img_a, img_b)
        loss = criterion(logits, label)

        if torch.isnan(loss):
            raise RuntimeError(f"Loss jadi NaN di step {step} -- smoke test GAGAL")

        loss.backward()
        optimizer.step()
        losses.append(loss.item())

        if (step + 1) % log_every == 0 or step == 0:
            print(f"  step {step+1}/{n_steps} | loss={loss.item():.4f}")
        step += 1

    elapsed = time.time() - t0
    avg_first5 = sum(losses[:5]) / min(5, len(losses))
    avg_last5 = sum(losses[-5:]) / min(5, len(losses))
    print(f"\nRata-rata loss 5 step pertama : {avg_first5:.4f}")
    print(f"Rata-rata loss 5 step terakhir: {avg_last5:.4f}")
    print(f"Durasi smoke test: {elapsed:.1f} detik ({elapsed/n_steps:.2f} detik/step, device={DEVICE})")

    if avg_last5 < avg_first5:
        print("OK — loss menurun, training loop berfungsi dengan benar.")
    else:
        print("PERINGATAN — loss tidak menurun dalam smoke test ini. Dengan subset "
              "sekecil ini & step sesedikit ini, ini belum tentu bug (bisa jadi cuma "
              "butuh lebih banyak step) -- tapi perlu diperhatikan.")

    return losses


if __name__ == "__main__":
    smoke_test()
