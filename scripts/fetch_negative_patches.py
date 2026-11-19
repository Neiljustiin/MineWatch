"""
Fetch citra Sentinel-2 RGB asli (lewat Microsoft Planetary Computer STAC) untuk
tiap kandidat lokasi negatif, lalu simpan dalam format sama persis dengan
MineNetCD256 (imageA, imageB, label) supaya bisa langsung digabung ke training set.

Karena ini lokasi NEGATIF (bukan tambang, tidak ada perubahan relevan):
  - imageA & imageB = scene paling jernih (least cloud) dari 2 tanggal berbeda (atau sama
    kalau cuma 1 scene bagus yang ketemu)
  - label = mask kosong (semua 0) -> "tidak ada perubahan tambang"

Tested: jalan di CPU, tanpa GPU, koneksi internet ke planetarycomputer.microsoft.com.
"""
import csv
import os

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds

PATCH_PX = 256
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATES_CSV = os.path.join(BASE_DIR, "data", "negative_patches", "negative_patch_candidates.csv")
OUT_DIR = os.path.join(BASE_DIR, "data", "negative_patches", "patches")
os.makedirs(OUT_DIR, exist_ok=True)

catalog = pystac_client.Client.open(
    "https://planetarycomputer.microsoft.com/api/stac/v1",
    modifier=planetary_computer.sign_inplace,
)


def fetch_rgb_patch(lon_min, lat_min, lon_max, lat_max, max_cloud=20, limit=5):
    """Cari scene Sentinel-2 L2A paling jernih yang nutup bbox ini, ambil RGB patch-nya."""
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=[lon_min, lat_min, lon_max, lat_max],
        datetime="2022-01-01/2024-12-31",
        query={"eo:cloud_cover": {"lt": max_cloud}},
        sortby=[{"field": "eo:cloud_cover", "direction": "asc"}],
        limit=limit,
    )
    items = list(search.items())
    if not items:
        return None, None
    item = items[0]
    bands = {}
    for b in ("B04", "B03", "B02"):  # R, G, B
        href = item.assets[b].href
        with rasterio.open(href) as src:
            win_bounds = transform_bounds("EPSG:4326", src.crs, lon_min, lat_min, lon_max, lat_max)
            window = from_bounds(*win_bounds, transform=src.transform)
            data = src.read(1, window=window, out_shape=(PATCH_PX, PATCH_PX), resampling=rasterio.enums.Resampling.bilinear)
            bands[b] = data
    rgb = np.stack([bands["B04"], bands["B03"], bands["B02"]], axis=-1).astype(np.float32)
    # Sentinel-2 L2A reflectance scaling standar (/10000), lalu stretch sederhana ke 0-255
    rgb = np.clip(rgb / 10000.0, 0, 0.3) / 0.3 * 255
    rgb = rgb.astype(np.uint8)
    return rgb, item.properties.get("eo:cloud_cover")


def main():
    with open(CANDIDATES_CSV) as f:
        candidates = list(csv.DictReader(f))

    results = []
    for i, c in enumerate(candidates):
        lon_min, lat_min = float(c["lon_min"]), float(c["lat_min"])
        lon_max, lat_max = float(c["lon_max"]), float(c["lat_max"])
        label_name = f"{c['tile']}_{c['class_name']}_{i:03d}"
        try:
            rgb, cloud = fetch_rgb_patch(lon_min, lat_min, lon_max, lat_max)
            if rgb is None:
                print(f"[{i}] {label_name}: TIDAK ADA scene cocok, skip")
                continue
            img = Image.fromarray(rgb, mode="RGB")
            img.save(os.path.join(OUT_DIR, f"{label_name}_imageA.png"))
            img.save(os.path.join(OUT_DIR, f"{label_name}_imageB.png"))  # negatif: A==B, no change
            label = Image.fromarray(np.zeros((PATCH_PX, PATCH_PX), dtype=np.uint8), mode="L")
            label.save(os.path.join(OUT_DIR, f"{label_name}_label.png"))
            print(f"[{i}] {label_name}: OK (cloud_cover={cloud}%)")
            results.append({**c, "patch_id": label_name, "cloud_cover": cloud, "status": "ok"})
        except Exception as e:
            print(f"[{i}] {label_name}: GAGAL - {e}")
            results.append({**c, "patch_id": label_name, "cloud_cover": None, "status": f"error: {e}"})

    out_csv = os.path.join(BASE_DIR, "data", "negative_patches", "negative_patches_manifest.csv")
    with open(out_csv, "w", newline="") as f:
        fieldnames = list(results[0].keys()) if results else []
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
    n_ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\nSelesai: {n_ok}/{len(candidates)} patch berhasil diambil. Manifest: {out_csv}")


if __name__ == "__main__":
    main()
