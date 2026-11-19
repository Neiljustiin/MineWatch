"""
Precompute everything the dashboard shows, from the REAL MineWatch repo data --
MODEL VARIANT: detection = FC-Siam-diff v4 checkpoint output, NOT NDVI threshold.

Fork of build_data.py (NDVI version) with ONLY the detection step swapped, per the
documented swap plan in the huawei-ict-mining-competition skill
(references/dashboard.md): everything else (imagery, permits, crosscheck,
frontend/backend) is untouched -- this writes to a SEPARATE --out dir so the
NDVI dashboard keeps working unmodified side-by-side for comparison.

Run (needs rasterio/geopandas/torch -> system interpreter):
    /usr/bin/python3 pipeline/build_data_model.py \
        --repo /home/ubuntu/huawei-ict-illegal-mining \
        --checkpoint /home/ubuntu/huawei-ict-illegal-mining/checkpoints/production_v4_base64_reg_jasansky/best_model.pt \
        --out data_model

CATATAN JUJUR:
  - Model dilatih di MineNetCD256 + Jasansky patches (RGB Sentinel-2), dipakai di
    sini ke True_color GeoTIFF band resolusi tinggi -- sama persis input yang
    dipakai scripts/inference_pipeline.py (sudah ada, belum pernah divalidasi
    end-to-end di case riil sebelum ini).
  - Threshold inference = 0.5 (default), SAMA dengan yang dipakai evaluate.py
    buat angka v4 yang sudah dilaporkan -- supaya hasil di sini bisa dibandingkan.
  - Ini BUKAN klaim "model lebih baik dari NDVI" -- cuma alat pembanding visual
    di dashboard, angka harus dicek manual per-kasus sebelum dipakai di laporan.
"""
import argparse
import glob
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import geopandas as gpd
import rasterio
import torch
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from PIL import Image
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from case_registry import CASES, QUALITY_LABELS  # noqa: E402

REPO_SCRIPTS = None  # set in main() once --repo is known
CLIP_RADIUS_KM = 3.0
NEARBY_PERMIT_RADIUS_KM = 5.0
MAX_IMG_W = 1600
THUMB = 84
MIN_POLY_PX = 25
INFERENCE_THRESHOLD = 0.5


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- imagery ----
def find_band(folder, key):
    m = sorted(glob.glob(os.path.join(folder, f"*{key}*")))
    return m[0] if m else None


def pair_folders(repo, slug):
    base = os.path.join(repo, "data", "sentinel2_pilot", slug)
    before = sorted(glob.glob(os.path.join(base, "before_*")))
    after = sorted(glob.glob(os.path.join(base, "after_*")))
    before = [d for d in before if os.path.isdir(d)]
    after = [d for d in after if os.path.isdir(d)]
    if len(before) != 1 or len(after) != 1:
        raise RuntimeError(f"{slug}: expected exactly one before_/after_ folder, got {before} {after}")
    return before[0], after[0]


def common_grid(paths, max_w=MAX_IMG_W):
    bnds, res = [], []
    for p in paths:
        with rasterio.open(p) as r:
            if r.crs.to_epsg() != 4326:
                raise RuntimeError(f"unexpected CRS {r.crs} in {p}")
            bnds.append(r.bounds)
            res.append((abs(r.transform.a), abs(r.transform.e)))
    w = max(b.left for b in bnds); e = min(b.right for b in bnds)
    s = max(b.bottom for b in bnds); n = min(b.top for b in bnds)
    if w >= e or s >= n:
        raise RuntimeError("before/after frames do not overlap")
    rx = min(r[0] for r in res); ry = min(r[1] for r in res)
    width = int(round((e - w) / rx)); height = int(round((n - s) / ry))
    if max_w and width > max_w:
        scale = max_w / width
        width, height = max_w, int(round(height * scale))
    return (w, s, e, n), width, height


def read_on_grid(path, bounds, width, height, resampling=Resampling.bilinear):
    dst_t = from_bounds(*bounds, width, height)
    with rasterio.open(path) as r:
        out = np.zeros((r.count, height, width), dtype=np.float32)
        for b in range(r.count):
            reproject(
                source=rasterio.band(r, b + 1), destination=out[b],
                src_transform=r.transform, src_crs=r.crs,
                dst_transform=dst_t, dst_crs=r.crs, resampling=resampling,
            )
    return out


def stretch_rgb(arr):
    valid = arr.sum(axis=0) > 0
    out = np.zeros(arr.shape[1:] + (3,), dtype=np.uint8)
    for i in range(3):
        band = arr[i]
        v = band[valid] if valid.any() else band.ravel()
        lo, hi = np.percentile(v, 2), np.percentile(v, 98)
        if hi <= lo:
            hi = lo + 1
        out[..., i] = (np.clip((band - lo) / (hi - lo), 0, 1) ** 0.9 * 255).astype(np.uint8)
    return out


def build_imagery(repo, case, out_dir, model, device):
    """Same as build_data.py's build_imagery, but the loss/disturbance step runs
    the FC-Siam-diff model instead of a dNDVI threshold."""
    from model import FCSiamDiff  # noqa: F401 (imported for side effect check only)
    from inference_pipeline import to_tensor, mask_to_polygons  # noqa: E402

    bdir, adir = pair_folders(repo, case["slug"])
    tc_b, tc_a = find_band(bdir, "True_color"), find_band(adir, "True_color")
    for p in (tc_b, tc_a):
        if not p:
            raise RuntimeError(f"{case['slug']}: missing True_color file")

    bounds, W, H = common_grid([tc_b, tc_a])
    rgb_by_tag = {}
    for tag, tc in (("before", tc_b), ("after", tc_a)):
        rgb = stretch_rgb(read_on_grid(tc, bounds, W, H))
        rgb_by_tag[tag] = rgb
        Image.fromarray(rgb).save(os.path.join(out_dir, f"{tag}.jpg"), quality=86)
        im = Image.fromarray(rgb)
        side = min(im.size)
        cx, cy = im.size[0] // 2, im.size[1] // 2
        im.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)) \
          .resize((THUMB, THUMB), Image.LANCZOS).save(os.path.join(out_dir, f"thumb_{tag}.jpg"), quality=82)

    # --- model inference at full resolution (same grid used for display, capped MAX_IMG_W) ---
    fb, FW, FH = common_grid([tc_b, tc_a], max_w=None)
    rgb_b_full = stretch_rgb(read_on_grid(tc_b, fb, FW, FH))
    rgb_a_full = stretch_rgb(read_on_grid(tc_a, fb, FW, FH))

    mask = tiled_inference_local(model, rgb_b_full, rgb_a_full, device, threshold=INFERENCE_THRESHOLD)
    n_changed_px = int(mask.sum())
    log(f"    model: {n_changed_px:,}/{mask.size:,} px flagged ({n_changed_px/mask.size*100:.2f}%)")

    ft = from_bounds(*fb, FW, FH)
    loss_gdf = mask_to_polygons(mask, ft, "EPSG:4326", min_area_px=MIN_POLY_PX)

    # visual overlay: solid red where model flags change (role equivalent to ndvi_loss.png)
    rgba = np.zeros((FH, FW, 4), dtype=np.uint8)
    rgba[..., 0] = 230
    rgba[..., 1] = 40
    rgba[..., 2] = 40
    rgba[..., 3] = np.where(mask == 1, 200, 0).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").resize((W, H), Image.NEAREST).save(
        os.path.join(out_dir, "model_loss.png"), optimize=True)

    def date_of(folder):
        return os.path.basename(folder).split("_", 1)[1]

    with rasterio.open(tc_b) as rb, rasterio.open(tc_a) as ra:
        same_extent = tuple(round(x, 5) for x in rb.bounds) == tuple(round(x, 5) for x in ra.bounds)
    return {
        "bounds": [round(x, 6) for x in bounds],
        "width": W, "height": H,
        "before_date": date_of(bdir), "after_date": date_of(adir),
        "frames_same_extent": same_extent,
        "model_flagged_pixel_fraction": float(n_changed_px / mask.size),
        "native_px": [FW, FH],
    }, loss_gdf


@torch.no_grad()
def tiled_inference_local(model, img_before, img_after, device, patch=256, threshold=0.5):
    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def to_t(img_hwc_uint8):
        x = img_hwc_uint8.astype(np.float32) / 255.0
        x = (x - IMAGENET_MEAN) / IMAGENET_STD
        return torch.from_numpy(x.transpose(2, 0, 1)).float()

    h, w = img_before.shape[:2]
    mask = np.zeros((h, w), dtype=np.uint8)
    for y in range(0, h, patch):
        for x in range(0, w, patch):
            y_end, x_end = min(y + patch, h), min(x + patch, w)
            tb, ta = img_before[y:y_end, x:x_end], img_after[y:y_end, x:x_end]
            th, tw = tb.shape[:2]
            if th < patch or tw < patch:
                tb = np.pad(tb, ((0, patch - th), (0, patch - tw), (0, 0)), mode="reflect")
                ta = np.pad(ta, ((0, patch - th), (0, patch - tw), (0, 0)), mode="reflect")
            t_b = to_t(tb).unsqueeze(0).to(device)
            t_a = to_t(ta).unsqueeze(0).to(device)
            logits = model(t_b, t_a)
            pred = (torch.sigmoid(logits) > threshold).squeeze().cpu().numpy().astype(np.uint8)
            mask[y:y_end, x:x_end] = pred[:th, :tw]
    return mask


# ---------------------------------------------------------------- permits ----
def load_permits(repo):
    sys.path.insert(0, os.path.join(repo, "scripts"))
    import permit_crosscheck as pc
    return pc, pc.load_permit_database()


def ms_to_date(v):
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return None
        return datetime.fromtimestamp(int(v) / 1000, tz=timezone.utc).date().isoformat()
    except Exception:
        return None


def permit_record(row, pc, ref_date, ref_point, overlap_ha=None, pct=None):
    end = ms_to_date(row.get("datend"))
    start = ms_to_date(row.get("datstr"))
    state = "unknown" if end is None else ("active" if end >= ref_date else "expired")
    geom = row.geometry
    nearest = geom.boundary.interpolate(geom.boundary.project(ref_point)) if not geom.contains(ref_point) else ref_point
    dist_km = 0.0 if geom.contains(ref_point) else pc._geodesic_distance_km(ref_point, nearest)
    return {
        "objectid": int(row["objectid"]), "name": row["permit_name"] or "(name not recorded)",
        "sk": row.get("skblok") or "-", "type": row.get("tiptmb") or "-", "commodity": row.get("commdt") or "-",
        "issuer": row.get("issuer") or "-", "status_code": row.get("status"),
        "valid_from": start, "valid_until": end, "state": state,
        "area_ha": round(pc._geodesic_area_ha(geom), 1), "distance_km": round(dist_km, 2),
        "overlap_ha": None if overlap_ha is None else round(overlap_ha, 2),
        "pct_of_disturbance": None if pct is None else round(pct, 1),
    }


def geodesic_circle(lon, lat, km):
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    utm = pt.estimate_utm_crs()
    return pt.to_crs(utm).buffer(km * 1000, resolution=64).to_crs("EPSG:4326").iloc[0]


def crosscheck_case(repo, case, pc, permits, ref_date, dist):
    if dist is None or dist.empty:
        return None, None
    circle = geodesic_circle(case["lon"], case["lat"], CLIP_RADIUS_KM)
    clipped = dist.copy()
    clipped["geometry"] = dist.geometry.intersection(circle)
    clipped = clipped[~clipped.geometry.is_empty & ~clipped.geometry.isna()]
    clipped = clipped[clipped.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if clipped.empty:
        return None, None

    canon = pc.crosscheck(clipped[["geometry"]], case_name=case["slug"], case_label=case["loc"],
                          search_buffer_km=CLIP_RADIUS_KM)

    union = clipped.geometry.union_all()
    total_ha = sum(pc._geodesic_area_ha(g) for g in clipped.geometry)
    buf = CLIP_RADIUS_KM / 111.0
    minx, miny, maxx, maxy = union.bounds
    cand = permits.iloc[list(permits.sindex.query(box(minx - buf, miny - buf, maxx + buf, maxy + buf),
                                                   predicate="intersects"))]
    ref_pt = union.centroid
    rows, active_parts, expired_parts = [], [], []
    for _, r in cand.iterrows():
        inter = union.intersection(r.geometry)
        ov = pc._geodesic_area_ha(inter) if not inter.is_empty else 0.0
        dcent = pc._geodesic_distance_km(ref_pt, r.geometry.centroid)
        if ov <= 0.01 and dcent > CLIP_RADIUS_KM:
            continue
        rec = permit_record(r, pc, ref_date, Point(case["lon"], case["lat"]), ov, ov / total_ha * 100 if total_ha else 0)
        rows.append(rec)
        if ov > 0:
            (active_parts if rec["state"] == "active" else expired_parts).append(inter)
    rows.sort(key=lambda x: (-(x["overlap_ha"] or 0), x["distance_km"]))

    active_u = unary_union(active_parts) if active_parts else None
    expired_u = unary_union(expired_parts) if expired_parts else None
    if expired_u is not None and active_u is not None:
        expired_u = expired_u.difference(active_u)
    in_active = pc._geodesic_area_ha(active_u) if active_u is not None and not active_u.is_empty else 0.0
    in_expired = pc._geodesic_area_ha(expired_u) if expired_u is not None and not expired_u.is_empty else 0.0
    outside = max(total_ha - in_active - in_expired, 0.0)

    result = {
        "method": f"FC-Siam-diff v4 model (checkpoint production_v4_base64_reg_jasansky, threshold "
                  f"{INFERENCE_THRESHOLD}), polygons clipped to {CLIP_RADIUS_KM:g} km of the case point, "
                  "vs BIG KSP permit polygons (~2022 baseline). Permit validity judged at the after-image date.",
        "radius_km": CLIP_RADIUS_KM,
        "disturbed_area_ha": canon["total_disturbed_area_ha"],
        "overlap_with_permits_ha": canon["total_overlap_with_any_permit_ha"],
        "outside_permits_ha": canon["outside_all_nearby_permits_ha"],
        "pct_outside_permits": canon["pct_outside_any_permit"],
        "n_permits_found_nearby": canon["n_permits_found_nearby"],
        "in_active_ha": round(in_active, 1), "in_expired_ha": round(in_expired, 1), "no_permit_ha": round(outside, 1),
        "validity_reference_date": ref_date, "permits": rows, "note": canon.get("note"),
        "polygon_source": "dashboard pipeline (pipeline/build_data_model.py), FC-Siam-diff v4 inference",
    }
    simplified = clipped.copy()
    simplified["geometry"] = simplified.geometry.simplify(0.00005, preserve_topology=True)
    return result, json.loads(simplified[["geometry"]].to_json())


def nearby_permits(case, pc, permits, ref_date, radius_km=NEARBY_PERMIT_RADIUS_KM):
    pt = Point(case["lon"], case["lat"])
    circle = geodesic_circle(case["lon"], case["lat"], radius_km)
    cand = permits.iloc[list(permits.sindex.query(circle, predicate="intersects"))]
    rows = [permit_record(r, pc, ref_date, pt) for _, r in cand.iterrows()]
    rows.sort(key=lambda x: x["distance_km"])
    return rows


def frame_permits_geojson(permits, bounds):
    w, s, e, n = bounds
    frame = box(w, s, e, n)
    sub = permits.iloc[list(permits.sindex.query(frame, predicate="intersects"))].copy()
    if sub.empty:
        return {"type": "FeatureCollection", "features": []}
    sub["geometry"] = sub.geometry.intersection(frame).simplify(0.00005, preserve_topology=True)
    feats = []
    for _, r in sub.iterrows():
        if r.geometry.is_empty:
            continue
        feats.append({"type": "Feature", "geometry": mapping(r.geometry),
                      "properties": {"objectid": int(r["objectid"]), "name": r["permit_name"],
                                     "valid_until": ms_to_date(r.get("datend")), "commodity": r.get("commdt")}})
    return {"type": "FeatureCollection", "features": feats}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/home/ubuntu/huawei-ict-illegal-mining")
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out", default=os.path.join(ROOT, "data_model"))
    args = ap.parse_args()

    sys.path.insert(0, os.path.join(args.repo, "scripts"))
    from model import FCSiamDiff  # noqa: E402

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log(f"loading checkpoint {args.checkpoint} (device={device}) ...")
    ckpt = torch.load(args.checkpoint, map_location=device, weights_only=False)
    model = FCSiamDiff(base_ch=ckpt["base_ch"]).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    log(f"  base_ch={ckpt['base_ch']} epoch={ckpt.get('epoch', '?')} val_loss={ckpt.get('val_loss', float('nan')):.4f}")

    log("loading permit database (BIG KSP) ...")
    pc, permits = load_permits(args.repo)
    log(f"  {len(permits)} permit polygons")

    out_cases = []
    for case in CASES:
        slug = case["slug"]
        log(f"[{case['id']}] {slug}")
        out_dir = os.path.join(args.out, "assets", slug)
        os.makedirs(out_dir, exist_ok=True)

        img, loss_gdf = build_imagery(args.repo, case, out_dir, model, device)
        ref_date = img["after_date"]

        cc, dist_geo = crosscheck_case(args.repo, case, pc, permits, ref_date, loss_gdf)
        if dist_geo is not None:
            json.dump(dist_geo, open(os.path.join(out_dir, "disturbance.geojson"), "w"))
        json.dump(frame_permits_geojson(permits, img["bounds"]), open(os.path.join(out_dir, "permits.geojson"), "w"))
        near = nearby_permits(case, pc, permits, ref_date)

        rec = dict(case)
        rec.update({
            "quality_label": QUALITY_LABELS[case["quality"]],
            "imagery": img,
            "crosscheck": cc,
            "nearby_permits": near,
            "nearby_radius_km": NEARBY_PERMIT_RADIUS_KM,
            "assets": {
                "before": f"/assets/{slug}/before.jpg", "after": f"/assets/{slug}/after.jpg",
                "ndvi_loss": f"/assets/{slug}/model_loss.png",  # same JSON key so frontend needs no changes
                "thumb_before": f"/assets/{slug}/thumb_before.jpg", "thumb_after": f"/assets/{slug}/thumb_after.jpg",
                "permits": f"/assets/{slug}/permits.geojson",
                "disturbance": f"/assets/{slug}/disturbance.geojson" if dist_geo is not None else None,
            },
        })
        out_cases.append(rec)
        msg = f"    model flagged={img['model_flagged_pixel_fraction']:.4f} px-fraction"
        if cc:
            msg += (f" | polys crosscheck {cc['disturbed_area_ha']} ha, outside {cc['pct_outside_permits']}%, "
                    f"active {cc['in_active_ha']} / expired {cc['in_expired_ha']} / none {cc['no_permit_ha']} ha")
        log(msg + f" | nearby permits {len(near)}")

    nat = permits[["objectid", "permit_name", "commdt", "datend", "prov", "kab", "tiptmb", "skblok", "geometry"]].copy()
    nat["geometry"] = nat.geometry.simplify(0.0005, preserve_topology=True)
    nat["valid_until"] = nat["datend"].map(ms_to_date)
    nat = nat.drop(columns=["datend"]).rename(columns={"permit_name": "name", "commdt": "commodity"})
    nat = nat[~nat.geometry.is_empty]
    nat.to_file(os.path.join(args.out, "permits.geojson"), driver="GeoJSON")
    log(f"wrote national permit layer ({len(nat)} polygons) -> data_model/permits.geojson")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_repo": args.repo,
        "permit_baseline": "BIG Kebijakan Satu Peta IUP/IUPK polygons, snapshot ~2022 (not real-time)",
        "permit_count": int(len(permits)),
        "detection_method": f"FC-Siam-diff model (checkpoint {os.path.basename(args.checkpoint)}), "
                             f"threshold {INFERENCE_THRESHOLD}. NOT NDVI -- AI model inference.",
        "checkpoint": args.checkpoint,
    }
    json.dump({"meta": meta, "cases": out_cases}, open(os.path.join(args.out, "cases.json"), "w"), indent=1)
    log(f"wrote {len(out_cases)} cases -> {os.path.join(args.out, 'cases.json')}")


if __name__ == "__main__":
    main()
