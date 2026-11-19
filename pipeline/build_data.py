"""
Precompute everything the dashboard shows, from the REAL MineWatch repo data.

Run (needs rasterio/geopandas -> use the system interpreter that has them):
    /usr/bin/python3 pipeline/build_data.py [--repo /home/ubuntu/huawei-ict-illegal-mining]

Outputs (all regenerated, safe to delete):
    data/cases.json                     one record per ground-truth case
    data/assets/<slug>/before.jpg       true colour, re-aligned to a common GeoTIFF grid
    data/assets/<slug>/after.jpg
    data/assets/<slug>/ndvi_loss.png    RGBA overlay of pixels with dNDVI < -0.2
    data/assets/<slug>/thumb_before.jpg, thumb_after.jpg
    data/assets/<slug>/permits.geojson  permit polygons intersecting the image frame
    data/assets/<slug>/disturbance.geojson  (only cases that have disturbance polygons)

What this script does NOT do: it does not run any AI model and does not invent a
detection for cases that have no disturbance polygons. Detection = NDVI threshold
(dNDVI < -0.2), exactly the method of scripts/compute_ndvi_ndmi.py.
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
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject
from rasterio.features import shapes as rio_shapes
from PIL import Image
from shapely.geometry import Point, box, mapping, shape
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from case_registry import CASES, QUALITY_LABELS  # noqa: E402

SHARP_LOSS_THRESHOLD = -0.2      # same as compute_ndvi_ndmi.py
CLIP_RADIUS_KM = 3.0             # same as analysis/polygon_crosscheck/*_clipped_3km
NEARBY_PERMIT_RADIUS_KM = 5.0    # context list for cases without disturbance polygons
MAX_IMG_W = 1600
THUMB = 84
MIN_POLY_PX = 25                 # noise filter, same as inference_pipeline.mask_to_polygons


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
    """Intersection of all rasters' bounds, at the finest pixel size among them."""
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
    if max_w and width > max_w:  # keep the web asset light
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
    """2-98 percentile stretch per band over valid pixels -> uint8 HxWx3."""
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


MAGMA = [(0.0, (0x57, 0x10, 0x6E)), (0.5, (0xBC, 0x37, 0x54)), (1.0, (0xF9, 0x8E, 0x09))]


def magma(t):
    t = np.clip(t, 0, 1)
    out = np.zeros(t.shape + (3,), dtype=np.float32)
    for (t0, c0), (t1, c1) in zip(MAGMA[:-1], MAGMA[1:]):
        m = (t >= t0) & (t <= t1)
        f = ((t - t0) / (t1 - t0))[m]
        for k in range(3):
            out[..., k][m] = c0[k] + (c1[k] - c0[k]) * f
    return out.astype(np.uint8)


def build_imagery(repo, case, out_dir):
    bdir, adir = pair_folders(repo, case["slug"])
    tc_b, tc_a = find_band(bdir, "True_color"), find_band(adir, "True_color")
    b4_b, b4_a = find_band(bdir, "B04"), find_band(adir, "B04")
    b8_b, b8_a = find_band(bdir, "B08"), find_band(adir, "B08")
    for p in (tc_b, tc_a, b4_b, b4_a, b8_b, b8_a):
        if not p:
            raise RuntimeError(f"{case['slug']}: missing band file")

    bounds, W, H = common_grid([tc_b, tc_a, b4_b, b4_a, b8_b, b8_a])
    for tag, tc in (("before", tc_b), ("after", tc_a)):
        rgb = stretch_rgb(read_on_grid(tc, bounds, W, H))
        Image.fromarray(rgb).save(os.path.join(out_dir, f"{tag}.jpg"), quality=86)
        im = Image.fromarray(rgb)
        side = min(im.size)
        cx, cy = im.size[0] // 2, im.size[1] // 2
        im.crop((cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)) \
          .resize((THUMB, THUMB), Image.LANCZOS).save(os.path.join(out_dir, f"thumb_{tag}.jpg"), quality=82)

    red_b = read_on_grid(b4_b, bounds, W, H)[0]; nir_b = read_on_grid(b8_b, bounds, W, H)[0]
    red_a = read_on_grid(b4_a, bounds, W, H)[0]; nir_a = read_on_grid(b8_a, bounds, W, H)[0]
    eps = 1e-6
    ndvi_b = (nir_b - red_b) / (nir_b + red_b + eps)
    ndvi_a = (nir_a - red_a) / (nir_a + red_a + eps)
    valid = ~(((nir_b == 0) & (red_b == 0)) | ((nir_a == 0) & (red_a == 0)))
    d = ndvi_a - ndvi_b
    loss = (d < SHARP_LOSS_THRESHOLD) & valid
    # colour: dNDVI -0.6 (deep purple) .. -0.2 (orange)
    t = (d + 0.6) / 0.4
    rgba = np.zeros((H, W, 4), dtype=np.uint8)
    rgba[..., :3] = magma(t)
    rgba[..., 3] = np.where(loss, 215, 0).astype(np.uint8)
    Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, "ndvi_loss.png"), optimize=True)

    # --- full-resolution loss polygons (same as inference_pipeline.mask_to_polygons, min 25 px)
    fb, FW, FH = common_grid([b4_b, b4_a, b8_b, b8_a], max_w=None)
    rb_ = read_on_grid(b4_b, fb, FW, FH)[0]; nb_ = read_on_grid(b8_b, fb, FW, FH)[0]
    ra_ = read_on_grid(b4_a, fb, FW, FH)[0]; na_ = read_on_grid(b8_a, fb, FW, FH)[0]
    v_ = ~(((nb_ == 0) & (rb_ == 0)) | ((na_ == 0) & (ra_ == 0)))
    d_ = (na_ - ra_) / (na_ + ra_ + eps) - (nb_ - rb_) / (nb_ + rb_ + eps)
    m_ = ((d_ < SHARP_LOSS_THRESHOLD) & v_).astype(np.uint8)
    ft = from_bounds(*fb, FW, FH)
    geoms = [shape(g) for g, _ in rio_shapes(m_, mask=(m_ == 1), transform=ft)]
    px = abs(ft.a * ft.e)
    geoms = [g for g in geoms if g.area > px * MIN_POLY_PX]
    loss_gdf = gpd.GeoDataFrame(geometry=geoms, crs="EPSG:4326")

    def date_of(folder):
        return os.path.basename(folder).split("_", 1)[1]

    with rasterio.open(tc_b) as rb, rasterio.open(tc_a) as ra:
        same_extent = tuple(round(x, 5) for x in rb.bounds) == tuple(round(x, 5) for x in ra.bounds)
    return {
        "bounds": [round(x, 6) for x in bounds],  # [west, south, east, north]
        "width": W, "height": H,
        "before_date": date_of(bdir), "after_date": date_of(adir),
        "frames_same_extent": same_extent,
        "aligned_sharp_loss_fraction": float(loss.sum() / max(valid.sum(), 1)),
        "native_px": [FW, FH],
    }, loss_gdf


# ---------------------------------------------------------------- permits ----
def load_permits(repo):
    sys.path.insert(0, os.path.join(repo, "scripts"))
    import permit_crosscheck as pc  # the canonical module from the MineWatch repo
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
    if end is None:
        state = "unknown"
    else:
        state = "active" if end >= ref_date else "expired"
    geom = row.geometry
    nearest = geom.boundary.interpolate(geom.boundary.project(ref_point)) if not geom.contains(ref_point) else ref_point
    dist_km = 0.0 if geom.contains(ref_point) else pc._geodesic_distance_km(ref_point, nearest)
    return {
        "objectid": int(row["objectid"]),
        "name": row["permit_name"] or "(name not recorded)",
        "sk": row.get("skblok") or "-",
        "type": row.get("tiptmb") or "-",
        "commodity": row.get("commdt") or "-",
        "issuer": row.get("issuer") or "-",
        "status_code": row.get("status"),
        "valid_from": start, "valid_until": end, "state": state,
        "area_ha": round(pc._geodesic_area_ha(geom), 1),
        "distance_km": round(dist_km, 2),
        "overlap_ha": None if overlap_ha is None else round(overlap_ha, 2),
        "pct_of_disturbance": None if pct is None else round(pct, 1),
    }


def geodesic_circle(lon, lat, km):
    """Circle as a polygon in EPSG:4326, built in the local UTM zone."""
    pt = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
    utm = pt.estimate_utm_crs()
    return pt.to_crs(utm).buffer(km * 1000, resolution=64).to_crs("EPSG:4326").iloc[0]


def crosscheck_case(repo, case, pc, permits, ref_date, dist):
    """NDVI-loss polygons clipped to 3 km of the case point, then cross-checked."""
    if dist is None or dist.empty:
        return None, None
    circle = geodesic_circle(case["lon"], case["lat"], CLIP_RADIUS_KM)
    clipped = dist.copy()
    clipped["geometry"] = dist.geometry.intersection(circle)
    clipped = clipped[~clipped.geometry.is_empty & ~clipped.geometry.isna()]
    clipped = clipped[clipped.geometry.geom_type.isin(["Polygon", "MultiPolygon"])]
    if clipped.empty:
        return None, None

    # 1) canonical numbers from the repo module (unchanged algorithm)
    canon = pc.crosscheck(clipped[["geometry"]], case_name=case["slug"], case_label=case["loc"],
                          search_buffer_km=CLIP_RADIUS_KM)

    # 2) same candidate search, enriched with permit validity -> active / expired split
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
        expired_u = expired_u.difference(active_u)   # active permit wins where both overlap
    in_active = pc._geodesic_area_ha(active_u) if active_u is not None and not active_u.is_empty else 0.0
    in_expired = pc._geodesic_area_ha(expired_u) if expired_u is not None and not expired_u.is_empty else 0.0
    outside = max(total_ha - in_active - in_expired, 0.0)

    result = {
        "method": f"NDVI threshold (dNDVI < {SHARP_LOSS_THRESHOLD}) polygons, clipped to {CLIP_RADIUS_KM:g} km of the case point, "
                  "vs BIG KSP permit polygons (~2022 baseline). Permit validity judged at the after-image date.",
        "radius_km": CLIP_RADIUS_KM,
        "disturbed_area_ha": canon["total_disturbed_area_ha"],
        "overlap_with_permits_ha": canon["total_overlap_with_any_permit_ha"],
        "outside_permits_ha": canon["outside_all_nearby_permits_ha"],
        "pct_outside_permits": canon["pct_outside_any_permit"],
        "n_permits_nearby": canon["n_permits_found_nearby"],
        "in_active_ha": round(in_active, 1),
        "in_expired_ha": round(in_expired, 1),
        "no_permit_ha": round(outside, 1),
        "validity_reference_date": ref_date,
        "permits": rows,
        "note": canon.get("note"),
        "polygon_source": "dashboard pipeline (pipeline/build_data.py) from the current before/after pair",
        "repo_reference": REPO_REFERENCE.get(case["slug"]),
    }
    simplified = clipped.copy()
    simplified["geometry"] = simplified.geometry.simplify(0.00005, preserve_topology=True)
    return result, json.loads(simplified[["geometry"]].to_json())


# Published figures from docs/KONTEKS_LENGKAP.md (BAGIAN 12, radius 3 km) for validation
REPO_REFERENCE = {
    "kembar_emas_sultra": {"disturbed_ha": 553, "outside_ha": 196, "pct_outside": 35},
    "das_kampak_bangkabarat": {"disturbed_ha": 374, "outside_ha": 261, "pct_outside": 70},
    "laroenai_morowali": {"disturbed_ha": 592, "outside_ha": 308, "pct_outside": 52},
}


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


# ------------------------------------------------------------------- main ----
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="/home/ubuntu/huawei-ict-illegal-mining")
    ap.add_argument("--out", default=os.path.join(ROOT, "data"))
    args = ap.parse_args()

    ndvi = json.load(open(os.path.join(args.repo, "analysis", "ndvi_ndmi", "ndvi_ndmi_results.json")))
    log("loading permit database (BIG KSP) ...")
    pc, permits = load_permits(args.repo)
    log(f"  {len(permits)} permit polygons")

    out_cases = []
    for case in CASES:
        slug = case["slug"]
        log(f"[{case['id']}] {slug}")
        if slug not in ndvi:
            raise RuntimeError(f"{slug} missing from ndvi_ndmi_results.json")
        n = ndvi[slug]
        out_dir = os.path.join(args.out, "assets", slug)
        os.makedirs(out_dir, exist_ok=True)

        img, loss_gdf = build_imagery(args.repo, case, out_dir)
        if img["before_date"] != n["before_date"] or img["after_date"] != n["after_date"]:
            raise RuntimeError(f"{slug}: image dates {img['before_date']}/{img['after_date']} != ndvi json "
                               f"{n['before_date']}/{n['after_date']}")
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
            "ndvi": {
                "before": n["before"], "after": n["after"],
                "delta_ndvi_mean": n["delta_ndvi_mean"], "delta_ndmi_mean": n["delta_ndmi_mean"],
                "veg_loss_percentage_points": n["veg_loss_percentage_points"],
                "sharp_ndvi_loss_pixel_fraction": n["sharp_ndvi_loss_pixel_fraction"],
                "sharp_ndvi_gain_pixel_fraction": n["sharp_ndvi_gain_pixel_fraction"],
            },
            "crosscheck": cc,
            "nearby_permits": near,
            "nearby_radius_km": NEARBY_PERMIT_RADIUS_KM,
            "assets": {
                "before": f"/assets/{slug}/before.jpg", "after": f"/assets/{slug}/after.jpg",
                "ndvi_loss": f"/assets/{slug}/ndvi_loss.png",
                "thumb_before": f"/assets/{slug}/thumb_before.jpg", "thumb_after": f"/assets/{slug}/thumb_after.jpg",
                "permits": f"/assets/{slug}/permits.geojson",
                "disturbance": f"/assets/{slug}/disturbance.geojson" if dist_geo is not None else None,
            },
        })
        out_cases.append(rec)
        msg = f"    dates {img['before_date']} -> {img['after_date']}  sharp loss json={n['sharp_ndvi_loss_pixel_fraction']:.3f} aligned={img['aligned_sharp_loss_fraction']:.3f}"
        if cc:
            msg += f"  | polys {len(loss_gdf)}"
            msg += f"  | crosscheck {cc['disturbed_area_ha']} ha, outside {cc['pct_outside_permits']}%, active {cc['in_active_ha']} / expired {cc['in_expired_ha']} / none {cc['no_permit_ha']} ha"
        log(msg + f"  | nearby permits {len(near)}")

    # national permit layer for the overview map (simplified ~50 m, key fields only)
    nat = permits[["objectid", "permit_name", "commdt", "datend", "prov", "kab", "tiptmb", "skblok", "geometry"]].copy()
    nat["geometry"] = nat.geometry.simplify(0.0005, preserve_topology=True)
    nat["valid_until"] = nat["datend"].map(ms_to_date)
    nat = nat.drop(columns=["datend"]).rename(columns={"permit_name": "name", "commdt": "commodity"})
    nat = nat[~nat.geometry.is_empty]
    nat.to_file(os.path.join(args.out, "permits.geojson"), driver="GeoJSON")
    log(f"wrote national permit layer ({len(nat)} polygons) -> data/permits.geojson")

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_repo": args.repo,
        "permit_baseline": "BIG Kebijakan Satu Peta IUP/IUPK polygons, snapshot ~2022 (not real-time)",
        "permit_count": int(len(permits)),
        "detection_method": f"NDVI threshold: pixel flagged when NDVI(after) - NDVI(before) < {SHARP_LOSS_THRESHOLD}. Not an AI model.",
        "sharp_loss_threshold": SHARP_LOSS_THRESHOLD,
    }
    json.dump({"meta": meta, "cases": out_cases}, open(os.path.join(args.out, "cases.json"), "w"), indent=1)
    log(f"wrote {len(out_cases)} cases -> {os.path.join(args.out, 'cases.json')}")


if __name__ == "__main__":
    main()
