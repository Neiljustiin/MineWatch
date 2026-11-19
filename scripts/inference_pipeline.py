"""
Pipeline END-TO-END: citra satelit (before/after GeoTIFF) -> model change
detection -> polygon gangguan -> cross-check database izin -> hasil
"flagged for review" (BUKAN vonis otomatis, sesuai prinsip proyek).

Ini yang menyambungkan Task 1 (dataset), Task 2 (model), dan Task 3
(permit_crosscheck) jadi satu alur utuh -- sebelumnya cuma ada di diagram,
belum pernah dites jalan beneran ujung ke ujung.

CARA KERJA:
  1. Baca GeoTIFF True_color before & after (biasanya 16-bit, >256x256 piksel)
  2. Normalisasi ke uint8 (percentile stretch per-band) -- True_color GeoTIFF
     dari Copernicus Browser itu 16-bit range lebar, bukan 0-255 standar.
  3. Potong (tile) jadi grid 256x256 (ukuran training), inference per-tile,
     gabung lagi (stitch) jadi mask prediksi seukuran citra asli.
  4. Vectorize mask (rasterio.features.shapes) jadi polygon di CRS asli.
  5. Filter polygon kekecilan (noise piksel, bukan area gangguan beneran).
  6. Panggil permit_crosscheck.crosscheck() -- HASIL AKHIR flagged for
     review, bukan keputusan "ilegal/legal" otomatis.

CATATAN JUJUR (belum divalidasi penuh, baca sebelum dipakai buat klaim):
  - Normalisasi uint16->uint8 pakai percentile stretch itu HEURISTIK buat
    demo, bukan kalibrasi radiometrik yang divalidasi scientifically.
  - Domain gap: model dilatih di MineNetCD256 (campuran sumber citra
    perubahan lahan), dipakai di sini ke Sentinel-2 True_color -- performa
    di domain baru ini belum diukur (beda dari metrik evaluate.py yang
    pakai data test SAMA domain dengan training).
  - Threshold confidence (0.5 default) belum di-tuning khusus buat use-case
    ini.
  Tujuan script ini: BUKTIKAN alurnya jalan secara teknis, bukan klaim
  akurasi deteksi mining ilegal yang sudah tervalidasi.
"""
import argparse
import os
import sys

import numpy as np
import rasterio
import rasterio.features
import geopandas as gpd
import torch
from shapely.geometry import shape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from model import FCSiamDiff  # noqa: E402
from permit_crosscheck import crosscheck  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
PATCH = 256


def load_and_stretch(path, low_pct=2, high_pct=98):
    """Baca GeoTIFF 3-band, percentile-stretch ke uint8 per band."""
    with rasterio.open(path) as src:
        arr = src.read().astype(np.float32)  # (bands, H, W)
        transform = src.transform
        crs = src.crs
    out = np.zeros_like(arr, dtype=np.uint8)
    for b in range(arr.shape[0]):
        lo, hi = np.percentile(arr[b], [low_pct, high_pct])
        band = np.clip((arr[b] - lo) / max(hi - lo, 1e-6), 0, 1)
        out[b] = (band * 255).astype(np.uint8)
    return out.transpose(1, 2, 0), transform, crs  # (H, W, 3)


def to_tensor(img_hwc_uint8):
    x = img_hwc_uint8.astype(np.float32) / 255.0
    x = (x - IMAGENET_MEAN) / IMAGENET_STD
    return torch.from_numpy(x.transpose(2, 0, 1)).float()


@torch.no_grad()
def tiled_inference(model, img_before, img_after, patch=PATCH, threshold=0.5):
    """Tile gambar jadi grid patch x patch, inference per-tile, stitch jadi mask penuh.
    Tile yang kepotong di tepi di-pad dulu (reflect), dipotong lagi pas stitch."""
    h, w = img_before.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)

    for y in range(0, h, patch):
        for x in range(0, w, patch):
            y_end, x_end = min(y + patch, h), min(x + patch, w)
            tile_before = img_before[y:y_end, x:x_end]
            tile_after = img_after[y:y_end, x:x_end]
            th, tw = tile_before.shape[:2]

            if th < patch or tw < patch:
                pad_before = np.pad(tile_before, ((0, patch - th), (0, patch - tw), (0, 0)), mode="reflect")
                pad_after = np.pad(tile_after, ((0, patch - th), (0, patch - tw), (0, 0)), mode="reflect")
            else:
                pad_before, pad_after = tile_before, tile_after

            t_before = to_tensor(pad_before).unsqueeze(0).to(DEVICE)
            t_after = to_tensor(pad_after).unsqueeze(0).to(DEVICE)
            logits = model(t_before, t_after)
            pred = (torch.sigmoid(logits) > threshold).squeeze().cpu().numpy().astype(np.uint8)

            mask[y:y_end, x:x_end] = pred[:th, :tw]

    return mask


def mask_to_polygons(mask, transform, crs, min_area_px=25):
    """Vectorize mask biner jadi GeoDataFrame polygon, filter noise kekecilan."""
    shapes_gen = rasterio.features.shapes(mask, mask=(mask == 1), transform=transform)
    geoms = []
    for geom_dict, value in shapes_gen:
        geom = shape(geom_dict)
        if geom.area > 0:
            geoms.append(geom)

    if not geoms:
        return gpd.GeoDataFrame(geometry=[], crs=crs)

    gdf = gpd.GeoDataFrame(geometry=geoms, crs=crs)
    # filter polygon piksel-tunggal/noise -- proxy kasar pakai luas piksel native
    # (bukan .geometry.area di CRS geografis, itu nggak akurat -- warning dari geopandas)
    px_area_deg2 = abs(transform.a * transform.e)
    gdf["_area_proxy_deg2"] = gdf.geometry.apply(lambda g: g.area)
    gdf = gdf[gdf["_area_proxy_deg2"] > px_area_deg2 * min_area_px].drop(columns="_area_proxy_deg2").reset_index(drop=True)
    return gdf


def run_pipeline(checkpoint_path, before_path, after_path, case_name, case_label="", threshold=0.5):
    print(f"=== Pipeline end-to-end: {case_name} ===")
    ckpt = torch.load(checkpoint_path, map_location=DEVICE, weights_only=False)
    model = FCSiamDiff(base_ch=ckpt["base_ch"]).to(DEVICE)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    print(f"Model base_ch={ckpt['base_ch']}, checkpoint epoch={ckpt.get('epoch', '?')}")

    print("Baca + normalisasi citra...")
    img_before, transform, crs = load_and_stretch(before_path)
    img_after, _, _ = load_and_stretch(after_path)
    print(f"Ukuran citra: {img_before.shape[:2]} piksel | CRS: {crs}")

    print("Inference tiled...")
    mask = tiled_inference(model, img_before, img_after, threshold=threshold)
    n_changed_px = int(mask.sum())
    print(f"Piksel terdeteksi 'berubah': {n_changed_px:,} / {mask.size:,} ({n_changed_px/mask.size*100:.2f}%)")

    print("Vectorize jadi polygon...")
    disturbance_gdf = mask_to_polygons(mask, transform, crs)
    print(f"Jumlah polygon (setelah filter noise): {len(disturbance_gdf)}")

    if len(disturbance_gdf) == 0:
        print("Tidak ada polygon gangguan terdeteksi -- tidak ada yang di-crosscheck.")
        return None

    print("Cross-check ke database izin resmi...")
    result = crosscheck(disturbance_gdf, case_name=case_name, case_label=case_label)

    print(f"\n--- HASIL (flagged for review, BUKAN vonis) ---")
    print(f"Total area terdeteksi berubah : {result.get('total_disturbed_area_ha', 0):.1f} ha")
    print(f"Di luar semua izin (flagged)  : {result.get('outside_all_nearby_permits_ha', 0):.1f} ha "
          f"({result.get('pct_outside_any_permit', 0):.1f}%)")
    print(f"Jumlah izin nearby ditemukan  : {result.get('n_permits_found_nearby', 0)}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--before", type=str, required=True)
    parser.add_argument("--after", type=str, required=True)
    parser.add_argument("--case-name", type=str, required=True)
    parser.add_argument("--case-label", type=str, default="")
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    run_pipeline(args.checkpoint, args.before, args.after, args.case_name, args.case_label, args.threshold)
