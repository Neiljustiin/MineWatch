"""
Generate kandidat lokasi patch negatif (bukan-tambang) dari tile ESA WorldCover.
Target kelas yang jadi sumber noise di demo cross-check sebelumnya:
  40 = Cropland (sawah/kebun)   50 = Built-up (bangunan/konstruksi)
  80 = Water bodies (air)       95 = Mangroves (pesisir/tidal)

Output: CSV berisi lat/lon bbox tiap kandidat patch (256x256 px @ 10m res = 2.56km x 2.56km),
siap dipakai buat fetch citra Sentinel-2 asli dari Planetary Computer.
"""
import csv
import os
import random

import numpy as np
import rasterio
from rasterio.windows import Window

PATCH_SIZE = 256  # px, sama dengan format MineNetCD256
TARGET_CLASSES = {40: "cropland", 50: "built_up", 80: "water", 95: "mangrove"}
N_PER_CLASS_PER_TILE = 6
PURITY_THRESHOLD = 0.7  # minimal 70% piksel dalam window harus kelas target

TILES = [
    ("S06E120", "Sulawesi"),
    ("S03E105", "Bangka"),
]

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "negative_patches",
)
os.makedirs(OUT_DIR, exist_ok=True)


def find_candidates(tile_path, tile_name, target_class, n_wanted, rng, purity_threshold=PURITY_THRESHOLD):
    found = []
    attempts = 0
    max_attempts = n_wanted * 2500  # batas biar gak infinite loop kalau kelas langka
    with rasterio.open(tile_path) as src:
        h, w = src.height, src.width
        while len(found) < n_wanted and attempts < max_attempts:
            attempts += 1
            row = rng.randint(0, h - PATCH_SIZE)
            col = rng.randint(0, w - PATCH_SIZE)
            window = Window(col, row, PATCH_SIZE, PATCH_SIZE)
            data = src.read(1, window=window)
            purity = (data == target_class).mean()
            if purity >= purity_threshold:
                bounds = rasterio.windows.bounds(window, src.transform)
                found.append({
                    "tile": tile_name,
                    "landcover_class": target_class,
                    "class_name": TARGET_CLASSES[target_class],
                    "purity": round(float(purity), 3),
                    "lon_min": bounds[0], "lat_min": bounds[1],
                    "lon_max": bounds[2], "lat_max": bounds[3],
                })
    return found, attempts


def main():
    rng = random.Random(42)
    all_candidates = []
    for tile_code, tile_name in TILES:
        tile_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "training_datasets", "esa_worldcover_tiles",
            f"ESA_WorldCover_10m_2021_v200_{tile_code}_Map.tif",
        )
        for cls, cls_name in TARGET_CLASSES.items():
            threshold = 0.25 if cls_name == "built_up" else PURITY_THRESHOLD
            found, attempts = find_candidates(tile_path, tile_name, cls, N_PER_CLASS_PER_TILE, rng, threshold)
            print(f"[{tile_name}] kelas {cls_name}: {len(found)}/{N_PER_CLASS_PER_TILE} ketemu ({attempts} percobaan, threshold={threshold})")
            all_candidates.extend(found)

    out_csv = os.path.join(OUT_DIR, "negative_patch_candidates.csv")
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_candidates[0].keys()))
        writer.writeheader()
        writer.writerows(all_candidates)
    print(f"\nTotal {len(all_candidates)} kandidat lokasi disimpan ke {out_csv}")


if __name__ == "__main__":
    main()
