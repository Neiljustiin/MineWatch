#!/usr/bin/env python3
"""
Hitung NDVI dan NDMI before/after untuk semua lokasi pilot MineWatch.

NDVI (Normalized Difference Vegetation Index) = (NIR - Red) / (NIR + Red)
  menggunakan band B08 (NIR) dan B04 (Red). Turun = kehilangan vegetasi.

NDMI (Normalized Difference Moisture Index, proxy bare-soil/vegetasi basah)
  = (NIR - SWIR) / (NIR + SWIR) menggunakan B08 dan B11.
  Turun tajam = tanah makin kering/terbuka (indikasi tambang).

CATATAN KETERBATASAN JUJUR: band B02 (Blue) TIDAK didownload di sesi
sebelumnya (cuma True color, B04, B08, B11), jadi BSI standar (Rikimaru et al,
butuh Blue) TIDAK bisa dihitung persis. Sebagai gantinya dipakai NDMI yang
cuma butuh NIR+SWIR (B08+B11) sebagai proxy soal exposure tanah/kekeringan.
Ini trade-off yang didokumentasikan, bukan disembunyikan.

Output per lokasi: nilai mean/median NDVI & NDMI before vs after, delta,
dan persentase piksel vegetasi (NDVI>0.3) yang hilang. Juga simpan PNG
visualisasi (before RGB | after RGB | NDVI delta heatmap).
"""
import glob
import json
import os
import sys

import numpy as np
from PIL import Image

BASE = "/home/ubuntu/huawei-ict-illegal-mining/data/sentinel2_pilot"
OUT_DIR = "/home/ubuntu/huawei-ict-illegal-mining/analysis/ndvi_ndmi"
os.makedirs(OUT_DIR, exist_ok=True)

NODATA_THRESHOLD_FRACTION = 0.5  # kalau >50% piksel nodata (B08==0), tandai curiga


def find_band(folder, band_name):
    matches = glob.glob(os.path.join(folder, f"*{band_name}*"))
    if not matches:
        return None
    return matches[0]


def load_band_as_float(path):
    img = Image.open(path)
    arr = np.array(img).astype(np.float64)
    return arr


def compute_indices(folder):
    b04_path = find_band(folder, "B04")
    b08_path = find_band(folder, "B08")
    b11_path = find_band(folder, "B11")
    tc_path = find_band(folder, "True_color")
    if not (b04_path and b08_path and b11_path):
        return None

    red = load_band_as_float(b04_path)
    nir = load_band_as_float(b08_path)
    swir = load_band_as_float(b11_path)

    # nodata mask: band yang bener2 0 di semua (B08==0 sering jadi tanda nodata
    # di tile Sentinel Hub kalau di luar cakupan citra)
    nodata_mask = (nir == 0) & (red == 0)
    nodata_frac = nodata_mask.mean()

    eps = 1e-6
    ndvi = (nir - red) / (nir + red + eps)
    ndmi = (nir - swir) / (nir + swir + eps)

    valid = ~nodata_mask
    ndvi_valid = ndvi[valid]
    ndmi_valid = ndmi[valid]

    result = {
        "ndvi_mean": float(np.mean(ndvi_valid)) if valid.any() else None,
        "ndvi_median": float(np.median(ndvi_valid)) if valid.any() else None,
        "ndmi_mean": float(np.mean(ndmi_valid)) if valid.any() else None,
        "ndmi_median": float(np.median(ndmi_valid)) if valid.any() else None,
        "veg_pixel_frac": float((ndvi_valid > 0.3).mean()) if valid.any() else None,
        "nodata_frac": float(nodata_frac),
        "valid_pixel_count": int(valid.sum()),
        "total_pixel_count": int(ndvi.size),
    }
    return result, ndvi, ndmi, nodata_mask, tc_path


def make_visualization(loc_name, before_tc, after_tc, ndvi_before, ndvi_after,
                        nodata_before, nodata_after, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    def load_tc(path):
        img = Image.open(path).convert("RGB")
        arr = np.array(img)
        # stretch sederhana 2-98 percentile biar kelihatan jelas
        p2, p98 = np.percentile(arr, (2, 98))
        arr = np.clip((arr.astype(float) - p2) / (p98 - p2 + 1e-6), 0, 1)
        return arr

    axes[0].imshow(load_tc(before_tc))
    axes[0].set_title("Before (True Color)")
    axes[0].axis("off")

    axes[1].imshow(load_tc(after_tc))
    axes[1].set_title("After (True Color)")
    axes[1].axis("off")

    ndvi_delta = ndvi_after - ndvi_before
    combined_nodata = nodata_before | nodata_after
    ndvi_delta_masked = np.ma.masked_where(combined_nodata, ndvi_delta)
    im = axes[2].imshow(ndvi_delta_masked, cmap="RdYlGn", vmin=-0.5, vmax=0.5)
    axes[2].set_title("NDVI Delta (merah=vegetasi hilang)")
    axes[2].axis("off")
    plt.colorbar(im, ax=axes[2], fraction=0.046, pad=0.04)

    fig.suptitle(loc_name, fontsize=14)
    plt.tight_layout()
    plt.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def main():
    locations = sorted(
        d for d in os.listdir(BASE)
        if os.path.isdir(os.path.join(BASE, d))
    )
    all_results = {}

    for loc in locations:
        loc_path = os.path.join(BASE, loc)
        subfolders = sorted(os.listdir(loc_path))
        before_folder = next((f for f in subfolders if f.startswith("before_")), None)
        after_folder = next((f for f in subfolders if f.startswith("after_")), None)
        if not (before_folder and after_folder):
            print(f"[SKIP] {loc}: before/after folder nggak lengkap ({subfolders})")
            continue

        before_path = os.path.join(loc_path, before_folder)
        after_path = os.path.join(loc_path, after_folder)

        before_calc = compute_indices(before_path)
        after_calc = compute_indices(after_path)

        if before_calc is None or after_calc is None:
            print(f"[SKIP] {loc}: band tidak lengkap")
            continue

        before_result, ndvi_b, ndmi_b, nodata_b, tc_b = before_calc
        after_result, ndvi_a, ndmi_a, nodata_a, tc_a = after_calc

        delta_ndvi_mean = (
            after_result["ndvi_mean"] - before_result["ndvi_mean"]
            if before_result["ndvi_mean"] is not None and after_result["ndvi_mean"] is not None
            else None
        )
        delta_ndmi_mean = (
            after_result["ndmi_mean"] - before_result["ndmi_mean"]
            if before_result["ndmi_mean"] is not None and after_result["ndmi_mean"] is not None
            else None
        )
        veg_loss_pct = (
            (before_result["veg_pixel_frac"] - after_result["veg_pixel_frac"]) * 100
            if before_result["veg_pixel_frac"] is not None and after_result["veg_pixel_frac"] is not None
            else None
        )

        # METRIK PIKSEL-LEVEL (bukan cuma mean frame): hitung piksel yang
        # NDVI-nya TURUN TAJAM (delta < -0.2) antara before -> after. Ini
        # deteksi "hotspot" kehilangan vegetasi lokal (indikasi pembukaan
        # lahan/tambang baru), tahan terhadap noise musiman/awan yang bisa
        # bikin rata-rata seluruh frame menyesatkan (lihat CATATAN di bawah).
        # Before/after redownload bisa beda dimensi pixel (zoom beda saat
        # ambil ulang citra). Resize ke shape yang lebih kecil (nearest-
        # neighbor via PIL) biar bisa dibandingkan piksel-per-piksel --
        # ini approksimasi kasar (bukan reproject geospasial presisi),
        # didokumentasikan sebagai keterbatasan di laporan.
        if ndvi_b.shape != ndvi_a.shape:
            target_shape = (min(ndvi_b.shape[0], ndvi_a.shape[0]), min(ndvi_b.shape[1], ndvi_a.shape[1]))
            def _resize(arr, shape):
                img = Image.fromarray(arr.astype(np.float32))
                return np.array(img.resize((shape[1], shape[0]), Image.NEAREST))
            def _resize_bool(arr, shape):
                img = Image.fromarray(arr.astype(np.uint8))
                return np.array(img.resize((shape[1], shape[0]), Image.NEAREST)).astype(bool)
            ndvi_b_r = _resize(ndvi_b, target_shape)
            ndvi_a_r = _resize(ndvi_a, target_shape)
            nodata_b_r = _resize_bool(nodata_b, target_shape)
            nodata_a_r = _resize_bool(nodata_a, target_shape)
        else:
            ndvi_b_r, ndvi_a_r, nodata_b_r, nodata_a_r = ndvi_b, ndvi_a, nodata_b, nodata_a

        combined_nodata = nodata_b_r | nodata_a_r
        valid_both = ~combined_nodata
        if valid_both.sum() > 0:
            pixel_delta = ndvi_a_r[valid_both] - ndvi_b_r[valid_both]
            sharp_loss_frac = float((pixel_delta < -0.2).mean())
            sharp_gain_frac = float((pixel_delta > 0.2).mean())
        else:
            sharp_loss_frac = None
            sharp_gain_frac = None

        entry = {
            "before_date": before_folder.replace("before_", ""),
            "after_date": after_folder.replace("after_", ""),
            "before": before_result,
            "after": after_result,
            "delta_ndvi_mean": delta_ndvi_mean,
            "delta_ndmi_mean": delta_ndmi_mean,
            "veg_loss_percentage_points": veg_loss_pct,
            "sharp_ndvi_loss_pixel_fraction": sharp_loss_frac,
            "sharp_ndvi_gain_pixel_fraction": sharp_gain_frac,
        }
        all_results[loc] = entry

        print(f"[{loc}] NDVI mean before={before_result['ndvi_mean']:.3f} "
              f"after={after_result['ndvi_mean']:.3f} delta={delta_ndvi_mean:.3f} | "
              f"sharp_loss_px={sharp_loss_frac:.1%} sharp_gain_px={sharp_gain_frac:.1%} | "
              f"nodata_before={before_result['nodata_frac']:.2%} "
              f"nodata_after={after_result['nodata_frac']:.2%}")

        # visualisasi
        if tc_b and tc_a:
            out_png = os.path.join(OUT_DIR, f"{loc}_ndvi_delta.png")
            try:
                make_visualization(loc, tc_b, tc_a, ndvi_b_r, ndvi_a_r, nodata_b_r, nodata_a_r, out_png)
            except Exception as e:
                print(f"  [WARN] gagal bikin visualisasi {loc}: {e}")

    out_json = os.path.join(OUT_DIR, "ndvi_ndmi_results.json")
    with open(out_json, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSelesai. {len(all_results)} lokasi diproses. Hasil JSON: {out_json}")


if __name__ == "__main__":
    main()
