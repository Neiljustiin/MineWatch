"""
Dataset loader untuk MineNetCD256 -- training corpus utama MineWatch.

Jalan di lab server tim (Proxmox LXC, RTX 3060 12GB) -- bukan lagi
ModelArts (scope GPU training dipindah ke lokal krn budget cloud terbatas,
konfirmasi 16 Nov 2026). OBS & ECS tetap dipakai buat bagian lain pipeline.

Dua lapisan di file ini:
  - `MineNetCDPatches`   : lapisan numpy/PIL murni, framework-agnostic.
  - `TorchMineNetCD`     : bungkus di atasnya jadi torch.utils.data.Dataset,
                           siap dipakai langsung di DataLoader.

CATATAN MEMORY PENTING (konsultasi RAM 16 Nov 2026, container cuma 12GB RAM):
Versi awal file ini pakai `pd.read_parquet()` -> load seluruh shard jadi
pandas DataFrame di __init__. Itu BERMASALAH kalau dipakai bareng
`DataLoader(num_workers>0)`: tiap worker di Linux di-fork, dan walau harusnya
copy-on-write, Python reference counting NYENTUH tiap row/object pandas pas
diakses -> compaction copy "diam-diam" kebawa, memory kealipat ~(num_workers+1)x.
Dengan subset data kita (train split ~1.2GB di disk), 4 worker bisa
bengkak jadi 5-6GB cuma gara-gara duplikasi ini -- riskan banget di RAM 12GB.

FIX: load pakai `pyarrow.parquet.read_table()`, simpan sebagai pyarrow Table
(bukan pandas DataFrame). Buffer Arrow hidup di luar Python heap dan TIDAK
disentuh refcounting per-row, jadi fork-safe -- worker proses cuma share
memory yang sama, bukan duplikat. Materialisasi ke Python object (dict/bytes)
cuma dilakukan per-item di `__getitem__`, bukan sekaligus di awal.
"""
import glob
import io
import os
import random

import numpy as np
import pyarrow.parquet as pq
from PIL import Image

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "training_datasets", "minenetcd256", "data",
)
# Patch Jasansky Indonesia (output jasansky_build_patches.py), skema parquet identik.
JASANSKY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "training_datasets", "jasansky_patches", "data",
)

SPLIT_FILES = {
    "train": sorted(glob.glob(os.path.join(DATA_DIR, "train-*.parquet"))),
    "val": sorted(glob.glob(os.path.join(DATA_DIR, "val-*.parquet"))),
    "test": sorted(glob.glob(os.path.join(DATA_DIR, "test-*.parquet"))),
    # Held-out lokasi Indonesia (TIDAK pernah dipakai training) -- buat klaim generalisasi domain.
    "jasansky_val": sorted(glob.glob(os.path.join(JASANSKY_DIR, "jasansky_val-*.parquet"))),
    "jasansky_train": sorted(glob.glob(os.path.join(JASANSKY_DIR, "jasansky_train-*.parquet"))),
}
# MINEWATCH_INCLUDE_JASANSKY=1 -> split 'train' = MineNetCD train + jasansky_train.
# Dibikin opt-in via env supaya run lama (v1/v2) tetap reproducible dan eval 'val'/'test'
# MineNetCD nggak berubah.
if os.environ.get("MINEWATCH_INCLUDE_JASANSKY") == "1":
    SPLIT_FILES["train"] = SPLIT_FILES["train"] + SPLIT_FILES["jasansky_train"]

_COLUMNS = ["imageA", "imageB", "label", "domain"]


class MineNetCDPatches:
    """Lazy-load patches dari parquet shard milik satu split (train/val/test).

    Fork-safe buat dipakai bareng DataLoader multi-worker -- lihat catatan
    memory di docstring module ini.
    """

    def __init__(self, split: str):
        if split not in SPLIT_FILES:
            raise ValueError(f"split harus salah satu dari {list(SPLIT_FILES)}")
        if not SPLIT_FILES[split]:
            raise FileNotFoundError(f"Parquet untuk split '{split}' tidak ketemu di {DATA_DIR}")
        self.split = split
        # pyarrow Table, BUKAN pandas DataFrame -- lihat catatan memory di atas.
        self._tables = [pq.read_table(f, columns=_COLUMNS) for f in SPLIT_FILES[split]]
        self._lengths = [t.num_rows for t in self._tables]
        self.total = sum(self._lengths)

    def __len__(self):
        return self.total

    def _locate(self, idx):
        for table, length in zip(self._tables, self._lengths):
            if idx < length:
                return table, idx
            idx -= length
        raise IndexError(idx)

    def __getitem__(self, idx):
        table, local_idx = self._locate(idx)
        # .slice(i, 1).to_pylist()[0] cuma materialisasi 1 ROW ke Python object,
        # sisanya di table tetap arrow buffer murni -- ini kuncinya hemat memory.
        row = table.slice(local_idx, 1).to_pylist()[0]
        image_a = np.array(Image.open(io.BytesIO(row["imageA"]["bytes"])).convert("RGB"))
        image_b = np.array(Image.open(io.BytesIO(row["imageB"]["bytes"])).convert("RGB"))
        label = np.array(Image.open(io.BytesIO(row["label"]["bytes"])).convert("L"))
        return {
            "image_before": image_a,
            "image_after": image_b,
            "label": label,
            "domain": row["domain"],
            "has_change": bool((label > 0).mean() > 0.01),
        }


# ---------------------------------------------------------------------------
# Lapisan PyTorch -- dipindah ke sini (sebelumnya didefinisikan duplikat di
# train.py) biar satu sumber kebenaran. Hanya bisa diimpor kalau torch
# terinstall di environment (lab server kita sudah ada, torch 2.5.1+cu121).
# ---------------------------------------------------------------------------
try:
    import torch
    from torch.utils.data import Dataset

    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    class TorchMineNetCD(Dataset):
        """Bungkus MineNetCDPatches (numpy-based) jadi Dataset PyTorch siap batch.

        augment=True (default utk split='train' saja -- lihat __init__) ngaktifin
        flip horizontal/vertical + rotasi kelipatan 90 derajat secara RANDOM per-item.
        Ini valid secara fisik buat citra satelit (nggak ada "atas" yang baku di
        permukaan bumi dari pandangan tegak lurus), beda sama augmentasi warna/crop
        yang bisa ngubah makna piksel. Ditambahin 16 Nov 2026 buat ngelawan overfitting
        yang kebukti dari gap train_loss vs val_loss di training v1/v2 (val_loss stuck
        /naik sementara train_loss terus turun -- model ngafalin training set, bukan
        generalisasi, krn variasi data terbatas tanpa augmentasi).
        PENTING: transform yang SAMA harus diterapin ke image_before, image_after,
        DAN label bareng -- kalau nggak, label jadi nggak nyambung sama piksel gambar.
        TIDAK diaktifin buat val/test (augmentasi cuma valid buat training, evaluasi
        harus tetap di data asli apa adanya biar metrik komparabel antar-run).
        """

        def __init__(self, split: str, subset_size: int | None = None, seed: int = 42, augment: bool | None = None):
            self.base = MineNetCDPatches(split)
            indices = list(range(len(self.base)))
            if subset_size is not None and subset_size < len(indices):
                rng = random.Random(seed)
                indices = rng.sample(indices, subset_size)  # SAMPLING ACAK, bukan berurutan
                # (pelajaran dari DATASET_MANIFEST.md: data terkelompok per domain,
                # subset berurutan bikin distribusi kelas bias)
            self.indices = indices
            # Default: augment ONLY di split train, kecuali di-override eksplisit.
            self.augment = augment if augment is not None else (split == "train")

        def __len__(self):
            return len(self.indices)

        def _to_chw_tensor(self, img_hwc_uint8):
            x = img_hwc_uint8.astype(np.float32) / 255.0
            x = (x - IMAGENET_MEAN) / IMAGENET_STD
            return torch.from_numpy(x.transpose(2, 0, 1)).float()

        def _apply_augment(self, image_before, image_after, label):
            # Flip + rotasi 90 derajat -- transform SAMA buat ketiga array (HWC/HW,
            # axis 0/1 = spasial, konsisten di image_before/after/label).
            if random.random() < 0.5:
                image_before = np.flip(image_before, axis=1).copy()
                image_after = np.flip(image_after, axis=1).copy()
                label = np.flip(label, axis=1).copy()
            if random.random() < 0.5:
                image_before = np.flip(image_before, axis=0).copy()
                image_after = np.flip(image_after, axis=0).copy()
                label = np.flip(label, axis=0).copy()
            k = random.randint(0, 3)
            if k:
                image_before = np.rot90(image_before, k, axes=(0, 1)).copy()
                image_after = np.rot90(image_after, k, axes=(0, 1)).copy()
                label = np.rot90(label, k, axes=(0, 1)).copy()
            return image_before, image_after, label

        def _apply_photometric(self, image_before, image_after):
            # Augmentasi fotometrik (16 Nov 2026): brightness/contrast +-10% dan
            # gaussian noise ringan. Tujuan: model nggak ngehafal nilai reflektansi
            # absolut scene tertentu (musim/sensor/atmosfer beda -> pixel value beda).
            # PENTING: faktor yang SAMA diterapin ke before & after -- kalau beda,
            # kita malah ngajarin model "perubahan palsu" dari pergeseran warna global.
            # Label TIDAK disentuh (hanya warna, bukan geometri).
            if random.random() < 0.5:
                return image_before, image_after
            contrast = random.uniform(0.9, 1.1)
            brightness = random.uniform(-0.1, 0.1) * 255.0
            noise_sigma = random.uniform(0.0, 3.0)  # skala 0-255

            def _adjust(img):
                x = img.astype(np.float32)
                mean = x.mean(axis=(0, 1), keepdims=True)
                x = (x - mean) * contrast + mean + brightness
                if noise_sigma > 0:
                    x = x + np.random.normal(0.0, noise_sigma, size=x.shape).astype(np.float32)
                return np.clip(x, 0, 255).astype(np.uint8)

            return _adjust(image_before), _adjust(image_after)

        def __getitem__(self, i):
            item = self.base[self.indices[i]]
            image_before, image_after, label = item["image_before"], item["image_after"], item["label"]
            if self.augment:
                image_before, image_after, label = self._apply_augment(image_before, image_after, label)
                image_before, image_after = self._apply_photometric(image_before, image_after)
            image_before = self._to_chw_tensor(image_before)
            image_after = self._to_chw_tensor(image_after)
            label = torch.from_numpy((label > 0).astype(np.float32)).unsqueeze(0)
            return image_before, image_after, label, item["has_change"]

except ImportError:
    TorchMineNetCD = None  # torch belum ada di environment ini


def sanity_check():
    print("=== Sanity check MineNetCD256 dataset loader (pyarrow, fork-safe) ===")
    rng = random.Random(42)
    for split in ("train", "val", "test"):
        ds = MineNetCDPatches(split)
        sample = ds[0]
        # PENTING: sampling HARUS acak, bukan N pertama berurutan -- data parquet
        # terkelompok per `domain`, jadi index berurutan bikin distribusi kelas bias
        # (lihat DATASET_MANIFEST.md). Pernah bug di sini sebelumnya, jangan diulang.
        checked = min(200, len(ds))
        sample_idx = rng.sample(range(len(ds)), checked)
        n_positive = sum(1 for i in sample_idx if ds[i]["has_change"])
        print(
            f"[{split}] total={len(ds)} | contoh shape image={sample['image_before'].shape} "
            f"label={sample['label'].shape} | domain contoh={sample['domain']} | "
            f"rasio patch 'ada perubahan' dari {checked} sample: {n_positive}/{checked} "
            f"({n_positive / checked * 100:.1f}%)"
        )
    print("\nOK -- loader berfungsi (pyarrow table, fork-safe buat multi-worker DataLoader).")
    if TorchMineNetCD is not None:
        print("torch terdeteksi -- TorchMineNetCD(Dataset) siap dipakai.")
    else:
        print("torch TIDAK terdeteksi di environment ini -- TorchMineNetCD tidak aktif.")


if __name__ == "__main__":
    sanity_check()
