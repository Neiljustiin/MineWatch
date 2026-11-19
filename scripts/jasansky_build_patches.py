"""
Bikin patch training 256x256 dari hasil download Jasansky (jasansky_stac_download.py)
dalam format parquet IDENTIK dengan MineNetCD256 (imageA/imageB/label struct{bytes,path},
domain string) -- supaya langsung bisa dibaca MineNetCDPatches tanpa loader baru.

Alur per tile (status 'done' di manifest.json):
  1. Baca before_*.tif, after_*.tif (B02,B03,B04,B08 uint16), *_scl.tif, label_polygon_mask.tif.
  2. RGB uint8: reflektansi B04/B03/B02 di-stretch 0..3000 -> 0..255 (stretch standar
     Sentinel-2 true-color; kira-kira setara tampilan Copernicus Browser).
  3. Potong grid 256x256 (stride 256, sisa pinggir dibuang).
  4. QA PER-PATCH (ini filter ketatnya, level tile sengaja longgar di downloader):
       - nodata (SCL 0/1) di before ATAU after > 2%  -> buang
       - awan/bayangan (SCL 3/8/9/10) di before ATAU after > 10% -> buang
  5. Label = polygon tambang Jasansky (area tambang di tanggal AFTER). Karena tile
     yang BEFORE-nya sudah tambang di-exclude di downloader, polygon ~= area yang
     berubah. Patch tanpa label tetap disimpan sebagai negatif (biar rasio
     positif/negatif nggak ekstrem), tapi di-cap maks NEG_PER_POS x jumlah positif.
  6. Split PER-LOKASI (tile), bukan per-patch: tile di-shuffle deterministik (seed 42),
     ~25% tile jadi 'jasansky_val' (held-out Indonesia, TIDAK dipakai training),
     sisanya 'jasansky_train'. Split per-patch bakal bocor (patch tetangga mirip).

Output: <out>/data/jasansky_train-00000.parquet, jasansky_val-00000.parquet, summary.json
"""
import argparse
import io
import json
import os
import random

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import rasterio
from PIL import Image

PATCH = 256
MAX_NODATA = 0.02
MAX_CLOUD = 0.10
NEG_PER_POS = 2.0
VAL_FRAC = 0.25
SEED = 42
STRETCH_MAX = 3000.0
SCL_NODATA = (0, 1)
SCL_CLOUD = (3, 8, 9, 10)  # kelas 7 (unclassified) sengaja TIDAK dihitung: di tropis terlalu banyak, bikin 80% patch kebuang
NDVI_BARE = 0.30
MIN_AFTER_MINE_PX = 2000        # ~0.2 km2 di 10 m; di bawah ini polygon dianggap nggak ada tambang terlihat
MIN_LABEL_PX = 2000             # total area ekspansi minimal per tile supaya tile punya sinyal positif nyata
MIN_BLOB_PX = 50                # blob label < 50 px (0.5 ha) dibuang: noise NDVI sporadis, bukan tambang
# ATURAN (diputuskan Neil 17 Nov 2026 dini hari): tile yang BEFORE-nya sudah ada tambang
# TIDAK dibuang lagi -> dipakai sebagai contoh EKSPANSI. Label turunan per-piksel udah
# otomatis kasih 0 ke area tambang lama dan 1 ke area ekspansi, jadi nggak lagi
# "ngajarin salah" seperti kalau pakai polygon mentah. Ini konsisten dengan MineNetCD
# (label = perubahan antar dua tanggal, bukan keberadaan tambang absolut).


def remove_small_blobs(mask, min_px):
    try:
        from scipy import ndimage
    except ImportError:
        return mask
    lab, n = ndimage.label(mask)
    if n == 0:
        return mask
    sizes = ndimage.sum(mask, lab, index=np.arange(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_px
    return keep[lab]


def ndvi(stack):
    red = stack[2].astype(np.float32)
    nir = stack[3].astype(np.float32)
    return (nir - red) / np.maximum(nir + red, 1.0)


def derive_change_label(before, after, scl_b, scl_a, poly):
    """Label perubahan per-piksel (16 Nov 2026, setelah cek visual):
    polygon Jasansky itu KASAR (poligon besar yang nyakup hutan/kebun), bukan outline
    tambang. Dipakai mentah -> model diajarin 'hutan = tambang'. Jadi label = di dalam
    polygon AND vegetasi di BEFORE (NDVI>=0.3) AND terbuka di AFTER (NDVI<0.3).
    Return (label_bool, info) dengan info buat aturan exclude: fraksi area tambang di
    AFTER yang SUDAH terbuka di BEFORE."""
    valid_b = ~np.isin(scl_b, SCL_NODATA + SCL_CLOUD)
    valid_a = ~np.isin(scl_a, SCL_NODATA + SCL_CLOUD)
    poly = poly > 0
    bare_b = ndvi(before) < NDVI_BARE
    bare_a = ndvi(after) < NDVI_BARE
    after_mine = poly & bare_a & valid_a & valid_b
    pre_existing = after_mine & bare_b
    label = remove_small_blobs(after_mine & ~bare_b, MIN_BLOB_PX)
    n_after = int(after_mine.sum())
    info = {
        "after_mine_px": n_after,
        "preexisting_frac": float(pre_existing.sum() / n_after) if n_after else None,
        "label_px": int(label.sum()),
    }
    return label, info


def to_rgb_uint8(stack):
    # stack: [B02,B03,B04,B08] uint16 -> RGB = B04,B03,B02
    rgb = np.stack([stack[2], stack[1], stack[0]], axis=-1).astype(np.float32)
    rgb = np.clip(rgb / STRETCH_MAX, 0, 1) * 255.0
    return rgb.astype(np.uint8)


def png_bytes(arr, mode):
    buf = io.BytesIO()
    Image.fromarray(arr, mode=mode).save(buf, format="PNG")
    return buf.getvalue()


def read_tile(tdir, qa):
    bd, ad = qa["before"]["date"], qa["after"]["date"]
    with rasterio.open(os.path.join(tdir, f"before_{bd}.tif")) as s:
        before = s.read()
    with rasterio.open(os.path.join(tdir, f"after_{ad}.tif")) as s:
        after = s.read()
    with rasterio.open(os.path.join(tdir, f"before_{bd}_scl.tif")) as s:
        scl_b = s.read(1)
    with rasterio.open(os.path.join(tdir, f"after_{ad}_scl.tif")) as s:
        scl_a = s.read(1)
    with rasterio.open(os.path.join(tdir, "label_polygon_mask.tif")) as s:
        label = s.read(1)
    return before, after, scl_b, scl_a, label


def patches_from_tile(tile_id, tdir, qa, rng):
    before, after, scl_b, scl_a, poly = read_tile(tdir, qa)
    label_full, info = derive_change_label(before, after, scl_b, scl_a, poly)
    stats = {"total": 0, "drop_nodata": 0, "drop_cloud": 0, "pos": 0, "neg_kept": 0, **info}
    # Aturan exclude (level tile): cuma kalau nggak ada tambang terlihat di AFTER, atau
    # area ekspansi (label) terlalu kecil buat jadi sinyal. "Before sudah tambang" BUKAN
    # alasan exclude lagi (contoh ekspansi) -- preexisting_frac tetap dicatat buat audit.
    if info["after_mine_px"] < MIN_AFTER_MINE_PX:
        stats["excluded"] = f"no_visible_mine_in_after ({info['after_mine_px']} px)"
        return [], stats
    if info["label_px"] < MIN_LABEL_PX:
        stats["excluded"] = f"expansion_too_small (label_px={info['label_px']}, preexisting={info['preexisting_frac']:.2f})"
        return [], stats
    rgb_b, rgb_a = to_rgb_uint8(before), to_rgb_uint8(after)
    H, W = label_full.shape
    pos, neg = [], []
    for y in range(0, H - PATCH + 1, PATCH):
        for x in range(0, W - PATCH + 1, PATCH):
            stats["total"] += 1
            sb = scl_b[y:y + PATCH, x:x + PATCH]
            sa = scl_a[y:y + PATCH, x:x + PATCH]
            if np.isin(sb, SCL_NODATA).mean() > MAX_NODATA or np.isin(sa, SCL_NODATA).mean() > MAX_NODATA:
                stats["drop_nodata"] += 1
                continue
            if np.isin(sb, SCL_CLOUD).mean() > MAX_CLOUD or np.isin(sa, SCL_CLOUD).mean() > MAX_CLOUD:
                stats["drop_cloud"] += 1
                continue
            lab = label_full[y:y + PATCH, x:x + PATCH].astype(np.uint8) * 255
            row = {
                "imageA": {"bytes": png_bytes(rgb_b[y:y + PATCH, x:x + PATCH], "RGB"), "path": f"t{tile_id}_{y}_{x}_A.png"},
                "imageB": {"bytes": png_bytes(rgb_a[y:y + PATCH, x:x + PATCH], "RGB"), "path": f"t{tile_id}_{y}_{x}_B.png"},
                "label": {"bytes": png_bytes(lab, "L"), "path": f"t{tile_id}_{y}_{x}_L.png"},
                "domain": f"Indonesia_jasansky_{tile_id}",
            }
            (pos if (lab > 0).mean() > 0.01 else neg).append(row)
    rng.shuffle(neg)
    neg = neg[: int(len(pos) * NEG_PER_POS)] if pos else neg[:4]
    stats.update(pos=len(pos), neg_kept=len(neg))
    return pos + neg, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="dir hasil jasansky_stac_download.py (ada manifest.json)")
    ap.add_argument("--out", required=True, help="dir output, akan dibuat <out>/data/*.parquet")
    ap.add_argument("--val-frac", type=float, default=VAL_FRAC, help="fraksi TILE jadi held-out; 1.0 = semua eval-only")
    args = ap.parse_args()

    manifest = json.load(open(os.path.join(args.src, "manifest.json")))
    # 'done' + 'excluded' (= before sudah tambang, file before/after LENGKAP tersimpan)
    # keduanya dipakai sejak aturan ekspansi; yang 'failed'/'error' nggak punya pasangan.
    done = sorted(int(t) for t, r in manifest.items()
                  if r.get("status") in ("done", "excluded") and r.get("before") and r.get("after"))
    if not done:
        raise SystemExit("Tidak ada tile status 'done' di manifest")
    rng = random.Random(SEED)

    os.makedirs(os.path.join(args.out, "data"), exist_ok=True)
    summary = {"per_tile": {}, "excluded_or_failed": {
        t: r.get("reason") for t, r in manifest.items() if int(t) not in done}}
    schema = pa.schema([
        ("imageA", pa.struct([("bytes", pa.binary()), ("path", pa.string())])),
        ("imageB", pa.struct([("bytes", pa.binary()), ("path", pa.string())])),
        ("label", pa.struct([("bytes", pa.binary()), ("path", pa.string())])),
        ("domain", pa.string()),
    ])
    # Pass 1: bikin patch semua tile 'done'; exclude strict terjadi di sini.
    per_tile_rows = {}
    for tid in done:
        tdir = os.path.join(args.src, f"tile_{tid}")
        qa = json.load(open(os.path.join(tdir, "qa.json")))
        prow, st = patches_from_tile(tid, tdir, qa, rng)
        summary["per_tile"][str(tid)] = st
        if "excluded" in st:
            summary["excluded_or_failed"][str(tid)] = st["excluded"]
            print(f"tile {tid}: EXCLUDED {st['excluded']}", flush=True)
            continue
        if st["pos"] == 0:
            summary["excluded_or_failed"][str(tid)] = "no_positive_patch_after_qa"
            print(f"tile {tid}: EXCLUDED no_positive_patch_after_qa {st}", flush=True)
            continue
        per_tile_rows[tid] = prow
        print(f"tile {tid}: {st}", flush=True)
    usable = sorted(per_tile_rows)
    if not usable:
        raise SystemExit("Tidak ada tile yang lolos QA/exclude")
    # Pass 2: split PER-LOKASI di antara tile yang beneran kepakai.
    tiles = usable[:]
    rng.shuffle(tiles)
    if args.val_frac >= 1.0:
        n_val = len(tiles)
    else:
        n_val = max(1, int(round(len(tiles) * args.val_frac))) if len(tiles) >= 4 else 0
    val_tiles, train_tiles = sorted(tiles[:n_val]), sorted(tiles[n_val:])
    summary.update(train_tiles=train_tiles, val_tiles=val_tiles)
    for split, tlist in (("jasansky_train", train_tiles), ("jasansky_val", val_tiles)):
        rows = []
        for tid in tlist:
            summary["per_tile"][str(tid)]["split"] = split
            rows.extend(per_tile_rows[tid])
        rng.shuffle(rows)
        table = pa.Table.from_pylist(rows, schema=schema)
        pq.write_table(table, os.path.join(args.out, "data", f"{split}-00000.parquet"), compression="zstd")
        summary[f"{split}_patches"] = len(rows)
        summary[f"{split}_positive"] = sum(summary["per_tile"][str(t)]["pos"] for t in tlist)
    with open(os.path.join(args.out, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k not in ("per_tile",)}, indent=1))


if __name__ == "__main__":
    main()
