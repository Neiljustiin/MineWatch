"""
Download citra Sentinel-2 L2A before/after untuk 47 tile Jasansky Indonesia
(Task 4) via STAC API Microsoft Planetary Computer -- BUKAN lewat UI
Copernicus Browser.

Kenapa STAC, bukan browser (pelajaran 16 Nov 2026):
  - UI Copernicus Browser rapuh buat batch: tab crash, tombol Download bisu
    (rate-limit), preview kecil nyesatin (nodata/awan nggak keliatan).
  - Planetary Computer nyediain produk Sentinel-2 L2A yang SAMA (ID produk
    identik, mis. S2A_MSIL2A_20181120T024001_R089_T49MHU_20201008T200613),
    tanpa login, bisa search per bbox+tanggal+cloud cover, dan baca windowed
    (cuma area tile, bukan scene 100km utuh).
  - Band SCL (scene classification) ikut ditarik -> QA awan/nodata OTOMATIS,
    bukan nebak dari screenshot.

Output per tile (di OUT_DIR/tile_<id>/):
  after_<date>.tif   : B02,B03,B04,B08 uint16 (reflektansi x10000), 10 m, LZW
  after_<date>_scl.tif
  before_<date>.tif  + _scl.tif (kalau ketemu kandidat lolos QA)
  qa.json            : metrik QA + flag exclude + alasan
Progress disimpan di OUT_DIR/manifest.json (resumable -- tile yang udah
'done'/'excluded' di-skip kalau script dijalankan ulang).

Aturan exclude (BINDING dari Neil): kalau citra BEFORE sudah menunjukkan
tambang, tile DIBUANG TOTAL. Di script ini dideteksi via proxy NDVI di dalam
polygon tambang Jasansky (preferred_polygons): kalau fraksi piksel
non-vegetasi (NDVI<0.3) di dalam polygon pada BEFORE sudah tinggi (>=0.5),
flag 'before_already_mined' -> excluded. Ambang ini heuristik; hasil flag
tetap harus dicek visual (lihat render PNG di scripts/jasansky_render_check.py).

CARA PAKAI (di server lab, venv /opt/minewatch/venv):
    python3 jasansky_stac_download.py --queue ../data/sentinel2_pilot/jasansky_indonesia_train_queue.json \
        --gpkg ../data/training_datasets/jasansky_masks/extracted/mining_area_data.gpkg \
        --out ../data/sentinel2_jasansky_stac [--only 2168,2121] [--limit N]
"""
import argparse
import datetime as dt
import json
import os
import re
import sqlite3
import sys
import time

import numpy as np
import planetary_computer
import pystac_client
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_bounds
from rasterio.warp import transform_bounds
from rasterio.windows import from_bounds as win_from_bounds
from shapely import wkb
from shapely.geometry import box, mapping

os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("GDAL_HTTP_MAX_RETRY", "5")
os.environ.setdefault("GDAL_HTTP_RETRY_DELAY", "3")

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTION = "sentinel-2-l2a"
BANDS = ["B02", "B03", "B04", "B08"]  # 10 m
RES_M = 10.0

# SCL: 0 nodata, 1 saturated/defective, 3 cloud shadow, 8 cloud med, 9 cloud high,
# 10 thin cirrus, 11 snow
SCL_NODATA = (0, 1)
SCL_CLOUD = (3, 8, 9, 10)

# Ambang QA (heuristik, dicatat di qa.json biar transparan).
# Level TILE sengaja longgar: tolak cuma kalau scene hopeless. Awan/nodata per-piksel
# tetap tersimpan di *_scl.tif, dan filter ketat dilakukan PER-PATCH 256x256 saat
# bikin dataset training (lihat jasansky_build_patches.py) -- lebih presisi daripada
# buang 1 tile 2048x2048 gara-gara awan di pojok.
MAX_NODATA_FRAC = 0.05
MAX_CLOUD_FRAC_TILE = 0.50
MAX_CLOUD_FRAC_POLY = 0.50          # AFTER (tanggal fixed dari label Jasansky)
BEFORE_STRICT_CLOUD_POLY = 0.10     # BEFORE: prioritas paling awal yang <= ini
BEFORE_LOOSE_CLOUD_POLY = 0.35      # fallback: paling bersih yang <= ini
BEFORE_MINED_NDVI = 0.30
BEFORE_MINED_FRAC = 0.50
S2_ARCHIVE_START = "2015-07-01"


def log(msg):
    print(f"[{dt.datetime.utcnow().strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- data sumber
def load_queue(path):
    with open(path) as f:
        q = json.load(f)
    out = []
    for d in q:
        m = re.search(r"_(\d{8})T\d{6}_", d["s2_tile_id"])
        d["after_date"] = f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:8]}"
        out.append(d)
    return out


def _gpkg_geom(blob):
    # GeoPackage binary: header 'GP' + version + flags + srs_id(4) + envelope
    flags = blob[3]
    env_type = (flags >> 1) & 0x07
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env_type]
    return wkb.loads(bytes(blob[8 + env_len:]))


def load_tile_geoms(gpkg, tile_id):
    c = sqlite3.connect(gpkg)
    trow = c.execute("select geom from tiles where tile_id=?", (tile_id,)).fetchone()
    polys = [_gpkg_geom(r[0]) for r in c.execute(
        "select geom from preferred_polygons where tile_id=?", (tile_id,))]
    c.close()
    return _gpkg_geom(trow[0]), polys


# ---------------------------------------------------------------- STAC
def stac_client():
    return pystac_client.Client.open(STAC_URL, modifier=planetary_computer.sign_inplace)


def get_item_by_id(client, item_id):
    try:
        return client.get_collection(COLLECTION).get_item(item_id)
    except Exception:
        return None


def search_after(client, tile_geom, after_date, s2_tile_id):
    # 1) coba ID produk persis (ID PC = ID produk ESA)
    item = get_item_by_id(client, s2_tile_id)
    if item is not None:
        return item, "exact_id"
    # 2) fallback: hari yang sama, tile MGRS yang sama
    mgrs = re.search(r"_T(\d{2}[A-Z]{3})_", s2_tile_id).group(1)
    d0 = dt.date.fromisoformat(after_date)
    rng = f"{d0.isoformat()}/{(d0 + dt.timedelta(days=1)).isoformat()}"
    items = list(client.search(collections=[COLLECTION], intersects=mapping(tile_geom),
                               datetime=rng).items())
    for it in items:
        if it.properties.get("s2:mgrs_tile") == mgrs:
            return it, "same_day_same_mgrs"
    if items:
        return items[0], "same_day_any"
    return None, "not_found"


def search_before_candidates(client, tile_geom, after_date, max_cc=50, min_gap_days=180):
    d_after = dt.date.fromisoformat(after_date)
    d_end = d_after - dt.timedelta(days=min_gap_days)
    if d_end <= dt.date.fromisoformat(S2_ARCHIVE_START):
        return []
    rng = f"{S2_ARCHIVE_START}/{d_end.isoformat()}"
    search = client.search(collections=[COLLECTION], intersects=mapping(tile_geom), datetime=rng,
                           query={"eo:cloud_cover": {"lt": max_cc}},
                           sortby=[{"field": "datetime", "direction": "asc"}], max_items=200)
    return list(search.items())


# ---------------------------------------------------------------- raster
def _grid_for(item, tile_geom):
    with rasterio.open(item.assets["B04"].href) as src:
        crs = src.crs
        b = transform_bounds("EPSG:4326", crs, *tile_geom.bounds)
    minx = np.floor(b[0] / RES_M) * RES_M
    miny = np.floor(b[1] / RES_M) * RES_M
    maxx = np.ceil(b[2] / RES_M) * RES_M
    maxy = np.ceil(b[3] / RES_M) * RES_M
    W = int(round((maxx - minx) / RES_M))
    H = int(round((maxy - miny) / RES_M))
    return crs, (minx, miny, maxx, maxy), W, H, from_bounds(minx, miny, maxx, maxy, W, H)


def read_scl_only(item, tile_geom):
    """Pre-screen murah: cuma SCL (20 m) di-resample ke grid 10 m tile."""
    crs, (minx, miny, maxx, maxy), W, H, transform = _grid_for(item, tile_geom)
    with rasterio.open(item.assets["SCL"].href) as src:
        win = win_from_bounds(minx, miny, maxx, maxy, src.transform)
        scl = src.read(1, window=win, out_shape=(H, W), boundless=True, fill_value=0,
                       resampling=rasterio.enums.Resampling.nearest).astype(np.uint8)
    return scl, transform, crs


def read_window(item, tile_geom):
    """Baca B02..B08 + SCL buat bbox tile, resample ke grid 10 m seragam.
    Return (stack uint16 [4,H,W], scl uint8 [H,W], transform, crs)."""
    crs, (minx, miny, maxx, maxy), W, H, transform = _grid_for(item, tile_geom)
    bands = []
    for bname in BANDS:
        with rasterio.open(item.assets[bname].href) as src:
            win = win_from_bounds(minx, miny, maxx, maxy, src.transform)
            arr = src.read(1, window=win, out_shape=(H, W), boundless=True, fill_value=0,
                           resampling=rasterio.enums.Resampling.nearest)
            bands.append(arr.astype(np.uint16))
    with rasterio.open(item.assets["SCL"].href) as src:
        win = win_from_bounds(minx, miny, maxx, maxy, src.transform)
        scl = src.read(1, window=win, out_shape=(H, W), boundless=True, fill_value=0,
                       resampling=rasterio.enums.Resampling.nearest).astype(np.uint8)
    return np.stack(bands), scl, transform, crs


def qa_metrics(stack, scl, poly_mask):
    nodata = np.isin(scl, SCL_NODATA) | (stack[2] == 0)
    cloud = np.isin(scl, SCL_CLOUD)
    red = stack[2].astype(np.float32)
    nir = stack[3].astype(np.float32)
    ndvi = (nir - red) / np.maximum(nir + red, 1.0)
    valid_poly = poly_mask & ~nodata & ~cloud
    m = {
        "nodata_frac": float(nodata.mean()),
        "cloud_frac_tile": float(cloud.mean()),
        "cloud_frac_poly": float(cloud[poly_mask].mean()) if poly_mask.any() else None,
        "nodata_frac_poly": float(nodata[poly_mask].mean()) if poly_mask.any() else None,
        "ndvi_mean_poly": float(ndvi[valid_poly].mean()) if valid_poly.any() else None,
        "nonveg_frac_poly": float((ndvi[valid_poly] < BEFORE_MINED_NDVI).mean()) if valid_poly.any() else None,
        "ndvi_mean_tile": float(ndvi[~nodata & ~cloud].mean()) if (~nodata & ~cloud).any() else None,
    }
    return m


def qa_pass(m):
    if m["nodata_frac"] > MAX_NODATA_FRAC:
        return False, f"nodata {m['nodata_frac']:.2f} > {MAX_NODATA_FRAC}"
    if m["cloud_frac_tile"] > MAX_CLOUD_FRAC_TILE:
        return False, f"cloud tile {m['cloud_frac_tile']:.2f} > {MAX_CLOUD_FRAC_TILE}"
    if m["cloud_frac_poly"] is not None and m["cloud_frac_poly"] > MAX_CLOUD_FRAC_POLY:
        return False, f"cloud polygon {m['cloud_frac_poly']:.2f} > {MAX_CLOUD_FRAC_POLY}"
    if m["nodata_frac_poly"] is not None and m["nodata_frac_poly"] > MAX_NODATA_FRAC:
        return False, f"nodata polygon {m['nodata_frac_poly']:.2f}"
    return True, "ok"


def write_tif(path, arr, transform, crs, dtype):
    if arr.ndim == 2:
        arr = arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2],
                       count=arr.shape[0], dtype=dtype, crs=crs, transform=transform,
                       compress="lzw", tiled=True, blockxsize=256, blockysize=256) as dst:
        dst.write(arr.astype(dtype))


# ---------------------------------------------------------------- per tile
def process_tile(client, entry, gpkg, out_dir, before_max_candidates=15):
    tid = entry["tile_id"]
    tdir = os.path.join(out_dir, f"tile_{tid}")
    os.makedirs(tdir, exist_ok=True)
    tile_geom, polys = load_tile_geoms(gpkg, tid)
    result = {"tile_id": tid, "minetype1": entry["minetype1"], "minetype2": entry.get("minetype2"),
              "after_date_queue": entry["after_date"], "status": None, "reason": None,
              "after": None, "before": None, "before_candidates_tried": []}

    # ---- AFTER
    item, how = search_after(client, tile_geom, entry["after_date"], entry["s2_tile_id"])
    if item is None:
        result.update(status="failed", reason="after product not found in STAC")
        return result
    stack, scl, transform, crs = read_window(item, tile_geom)
    # polygon label ada di EPSG:4326, raster di UTM -> reproject geometri dulu baru rasterize
    poly_mask = np.zeros(scl.shape, bool)
    if polys:
        import rasterio.warp as rw
        polys_utm = [rw.transform_geom("EPSG:4326", crs, mapping(p)) for p in polys]
        poly_mask = rasterize([(g, 1) for g in polys_utm], out_shape=scl.shape, transform=transform,
                              fill=0, dtype=np.uint8).astype(bool)
    m_after = qa_metrics(stack, scl, poly_mask)
    ok, why = qa_pass(m_after)
    after_date = item.datetime.date().isoformat()
    result["after"] = {"item_id": item.id, "date": after_date, "match": how, "qa": m_after,
                       "qa_pass": ok, "qa_reason": why, "poly_frac_of_tile": float(poly_mask.mean())}
    if not ok:
        result.update(status="failed", reason=f"after QA gagal: {why}")
        return result
    write_tif(os.path.join(tdir, f"after_{after_date}.tif"), stack, transform, crs, "uint16")
    write_tif(os.path.join(tdir, f"after_{after_date}_scl.tif"), scl, transform, crs, "uint8")
    write_tif(os.path.join(tdir, "label_polygon_mask.tif"), poly_mask.astype(np.uint8), transform, crs, "uint8")
    log(f"  tile {tid}: AFTER ok {after_date} ({how}) cloud={m_after['cloud_frac_tile']:.2f} nodata={m_after['nodata_frac']:.2f}")

    # ---- BEFORE: evaluasi kandidat kronologis; pilih PALING AWAL yang lolos strict,
    # fallback PALING BERSIH yang lolos loose. Nodata tetap ketat.
    cands = search_before_candidates(client, tile_geom, after_date)
    if not cands:
        cands = search_before_candidates(client, tile_geom, after_date, max_cc=80)
    evaluated = []
    for cand in cands[:before_max_candidates]:
        try:
            scl_b, tr_b, crs_b = read_scl_only(cand, tile_geom)
        except Exception as e:  # noqa: BLE001
            result["before_candidates_tried"].append({"item_id": cand.id, "error": str(e)[:120]})
            continue
        if scl_b.shape != scl.shape or crs_b != crs:
            result["before_candidates_tried"].append({"item_id": cand.id, "error": "grid mismatch (beda UTM zone?)"})
            continue
        nodata = np.isin(scl_b, SCL_NODATA)
        cloud = np.isin(scl_b, SCL_CLOUD)
        nd_t = float(nodata.mean())
        nd_p = float(nodata[poly_mask].mean()) if poly_mask.any() else 0.0
        cp = float(cloud[poly_mask].mean()) if poly_mask.any() else float(cloud.mean())
        nodata_ok = nd_t <= MAX_NODATA_FRAC and nd_p <= MAX_NODATA_FRAC
        strict = nodata_ok and cp <= BEFORE_STRICT_CLOUD_POLY
        loose = nodata_ok and cp <= BEFORE_LOOSE_CLOUD_POLY
        result["before_candidates_tried"].append({"item_id": cand.id, "date": cand.datetime.date().isoformat(),
                                                  "scene_cc": cand.properties.get("eo:cloud_cover"),
                                                  "cloud_frac_poly": cp, "nodata_frac": nd_t,
                                                  "strict": strict, "loose": loose})
        log(f"    before cand {cand.datetime.date()} scene_cc={cand.properties.get('eo:cloud_cover')} "
            f"cloud_poly={cp:.2f} nodata={nd_t:.2f} strict={strict} loose={loose}")
        evaluated.append((cand, cp, strict, loose))
        if strict:
            break  # kandidat kronologis -> yang pertama strict = paling awal yang bersih
    chosen = None
    strict_ok = [e for e in evaluated if e[2]]
    loose_ok = [e for e in evaluated if e[3]]
    if strict_ok:
        chosen = strict_ok[0]
        result["before_pick_rule"] = "earliest_strict"
    elif loose_ok:
        chosen = min(loose_ok, key=lambda e: e[1])
        result["before_pick_rule"] = "cleanest_loose"
    if chosen is None:
        result.update(status="failed", reason="tidak ada kandidat BEFORE lolos QA")
        return result
    cand = chosen[0]
    st_b, scl_b, tr_b, crs_b = read_window(cand, tile_geom)
    m_b = qa_metrics(st_b, scl_b, poly_mask)
    before_date = cand.datetime.date().isoformat()
    result["before"] = {"item_id": cand.id, "date": before_date, "qa": m_b}
    write_tif(os.path.join(tdir, f"before_{before_date}.tif"), st_b, tr_b, crs_b, "uint16")
    write_tif(os.path.join(tdir, f"before_{before_date}_scl.tif"), scl_b, tr_b, crs_b, "uint8")

    # ---- aturan exclude: before sudah tambang?
    nonveg_b = m_b.get("nonveg_frac_poly")
    nonveg_a = m_after.get("nonveg_frac_poly")
    result["exclude_check"] = {"nonveg_frac_poly_before": nonveg_b, "nonveg_frac_poly_after": nonveg_a,
                               "threshold": BEFORE_MINED_FRAC}
    if nonveg_b is not None and nonveg_b >= BEFORE_MINED_FRAC:
        result.update(status="excluded", reason=f"before_already_mined (nonveg di polygon before={nonveg_b:.2f})")
    else:
        result.update(status="done", reason="ok")
    with open(os.path.join(tdir, "qa.json"), "w") as f:
        json.dump(result, f, indent=2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True)
    ap.add_argument("--gpkg", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", default=None, help="comma-separated tile_id")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--redo", action="store_true", help="proses ulang tile yang sudah ada di manifest")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    man_path = os.path.join(args.out, "manifest.json")
    manifest = json.load(open(man_path)) if os.path.exists(man_path) else {}
    queue = load_queue(args.queue)
    if args.only:
        keep = {int(x) for x in args.only.split(",")}
        queue = [q for q in queue if q["tile_id"] in keep]
    if args.limit:
        queue = queue[: args.limit]

    client = stac_client()
    t0 = time.time()
    for i, entry in enumerate(queue, 1):
        tid = str(entry["tile_id"])
        if tid in manifest and manifest[tid].get("status") in ("done", "excluded") and not args.redo:
            log(f"[{i}/{len(queue)}] tile {tid} skip (sudah {manifest[tid]['status']})")
            continue
        log(f"[{i}/{len(queue)}] tile {tid} ({entry['minetype1']}, after {entry['after_date']})")
        try:
            res = process_tile(client, entry, args.gpkg, args.out)
        except Exception as e:  # noqa: BLE001
            res = {"tile_id": entry["tile_id"], "status": "error", "reason": f"{type(e).__name__}: {str(e)[:200]}"}
            log(f"  ERROR tile {tid}: {res['reason']}")
        manifest[tid] = res
        with open(man_path, "w") as f:
            json.dump(manifest, f, indent=2)
        log(f"  -> {res['status']}: {res.get('reason')}")

    summary = {}
    for r in manifest.values():
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    log(f"SELESAI {time.time() - t0:.0f}s. Ringkasan: {summary}")


if __name__ == "__main__":
    sys.exit(main())
