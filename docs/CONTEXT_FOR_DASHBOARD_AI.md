# MineWatch Dashboard — Context for AI coding assistant

> Read this before writing code. This describes the REAL project state, REAL data files,
> and REAL constraints — not the pitch-deck version. If something here conflicts with a
> prompt you're given, this file wins; ask the user if genuinely unsure.

## What this project is

MineWatch is an illegal mining detection tool for Indonesia (Huawei ICT Competition
Innovation Track entry, team "kulonuwun"). Pipeline: satellite change-detection →
cross-check against mining permit polygons → flag suspect sites → human analyst reviews
→ (future) alert to DLHK/Polda. This dashboard is the **analyst-facing web UI** on top of
that pipeline — it is the part being built right now.

## Stack reality check — what's actually Huawei vs not

Only **2 Huawei Cloud services are in use**: ECS (compute for the ingestion/NDVI
pipeline) and OBS (object storage for raw Sentinel-2 GeoTIFFs). Everything downstream —
AI model, cross-check logic, backend API, and this dashboard — is self-built / runs on
our own resources. Do NOT assume ModelArts, GaussDB, DataArts, API Gateway, Astro, or SMN
are available or in use. If the dashboard needs a backend, it should be a plain custom
API (e.g. FastAPI/Express), not a Huawei managed service.

## Current pipeline status (what exists vs what's still manual/offline)

- 13 ground-truth cases, geocoded, Sentinel-2 GeoTIFF downloaded (before/after, bands:
  True color, B04, B08, B11).
- NDVI/NDMI computed per case (`scripts/compute_ndvi_ndmi.py`) — results in
  `analysis/ndvi_ndmi/ndvi_ndmi_results.json`.
- Reliability per case (manual cloud QC): 3 reliable, 2 light caveat, 3 medium caveat,
  5 unreliable (cloud-contaminated, need redownload). See
  `analysis/ndvi_ndmi/HASIL_NDVI_NDMI.md` for per-case reasoning.
- Permit cross-check done for the 3 reliable cases only, via geopandas (local, not a
  managed DB) — results in `analysis/polygon_crosscheck/crosscheck_results_clipped_3km.json`.
- Permit baseline: 4,608 IUP/IUPK polygons from BIG KSP (public), snapshot ~2022, NOT
  real-time. File: `data/momi_processed/iup_izin_tambang_big_satupeta_merged.geojson`.
- Trained AI change-detection model (U-Net/DeepLabV3+): NOT trained yet. Training datasets
  are assembled (`data/training_datasets/`, see `DATASET_MANIFEST.md`) but no GPU
  available in current dev env. **The dashboard will initially display pre-computed
  NDVI-threshold results, not live trained-model inference.**
- Backend API, this dashboard: being built now (your job).
- Alerting (email/webhook to DLHK/Polda): not built, roadmap only — do not build a "send
  alert" button that actually sends anything real yet; it should be a no-op/mock.

## Real data schemas to build the dashboard against

### `ndvi_ndmi_results.json` — per-case NDVI/NDMI (keyed by case slug)
```json
{
  "<case_slug>": {
    "before_date": "2019-11-07",
    "after_date": "2026-05-19",
    "before": { "ndvi_mean": 0.665, "ndvi_median": 0.696, "ndmi_mean": 0.288,
                "ndmi_median": 0.303, "veg_pixel_frac": 0.963, "nodata_frac": 0.0,
                "valid_pixel_count": 1244985, "total_pixel_count": 1244985 },
    "after": { "...same shape as before..." },
    "delta_ndvi_mean": 0.180,
    "delta_ndmi_mean": 0.057,
    "veg_loss_percentage_points": -0.92,
    "sharp_ndvi_loss_pixel_fraction": 0.031,
    "sharp_ndvi_gain_pixel_fraction": 0.391
  }
}
```
`sharp_ndvi_loss_pixel_fraction` is the key metric used for "disturbance detected" — NOT
the simple mean delta (area is usually a small fraction of the frame).

### `crosscheck_results_clipped_3km.json` — permit overlay (array, only 3 cases so far)
```json
[
  { "case": "kembar_emas_sultra", "name": "PT Kembar Emas Sultra (PT KES), Konawe Utara",
    "radius_km": 3.0, "disturbed_area_ha": 553.3, "overlap_with_permits_ha": 357.7,
    "outside_permits_ha": 195.6, "pct_outside_permits": 35.4, "n_permits_nearby": 8 }
]
```
`pct_outside_permits` is effectively the "suspect illegal" signal used for the
HIJAU/KUNING/MERAH status (higher % outside permits → more MERAH-leaning), but there is
**no hard threshold rule defined yet** — this needs a product decision before the
dashboard can auto-classify it; don't invent a magic number silently.

### Status taxonomy (must match exactly, including Indonesian labels in UI)
- `HIJAU` — inside an active valid permit = legal
- `KUNING` — permit exists but expired
- `MERAH` — no matching permit = flagged for review (NOT an automatic legal verdict)

### Other files worth knowing about
- `data/sentinel2_pilot/<case_slug>/{before,after}_<date>/*.tiff` — raw GeoTIFFs per case
  (True color + 3 raw bands), used for before/after image comparison UI.
- `analysis/ndvi_ndmi/<case_slug>_ndvi_delta.png` — pre-rendered delta heatmap images,
  usable directly as the NDVI overlay in the UI without recomputing.
- `analysis/polygon_crosscheck/<case_slug>_disturbance_polygons.geojson` — vector polygons
  of detected disturbance, for map overlay.
- `docs/HASIL_NDVI_NDMI.md` and `docs/KONTEKS_LENGKAP.md` — full narrative history/decisions,
  read these if you need "why" not just "what".

## Product/UX decisions already locked in (don't relitigate without asking)

- Human-in-the-loop: AI/threshold output is always "flagged for review", analyst makes
  the final call (Confirmed illegal / Needs field verification / False positive / Legal)
  before anything is "sent" anywhere.
- Visual reference/inspiration used for this UI: Satelligence (event feed + map + detail
  timeline), Global Forest Watch (layer legend, confidence levels), Nusantara Atlas
  (Indonesia-specific mining/deforestation map), Kontur Disaster Ninja/UI Kit (dense ops
  panel style). Avoid generic "AI dashboard" look (no purple gradients, no decorative
  glassmorphism, no fake stock imagery).
- Only 13 ground-truth cases exist total, and only 3 have full cross-check data — design
  the UI to look reasonable with that small, real dataset (don't assume hundreds of live
  records; don't fabricate placeholder data in seed/demo mode without labeling it as demo).

## Honesty rules for this project (apply to code, copy, and demo data alike)

- Never present NDVI-threshold output as "AI model result" — label it explicitly as
  threshold-based detection until a trained model actually exists.
- Never let a UI control imply an action happened (e.g. "Alert sent to DLHK") unless that
  integration is real; mock actions must be visibly marked as mock/disabled in dev.
- Permit data is ~2022 baseline — if displayed, note it's not current, don't imply
  real-time legal status.
