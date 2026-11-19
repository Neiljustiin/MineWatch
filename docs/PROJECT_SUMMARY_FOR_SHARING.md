# MineWatch — What We Actually Do (status 16 Nov 2026)

## Problem we're solving
Illegal mining detection in Indonesia: AI-based change detection on satellite imagery,
cross-checked against official permit (IUP/IUPK) data, to flag suspect illegal mining
sites for human review.

## What's actually built right now

- **13 ground-truth cases** collected & geocoded from verified sources (Kejagung, BPKP,
  Satgas PKH, mainstream news) — spans Jambi, Papua, Sulawesi, Kalimantan, Bangka Belitung.
- **Sentinel-2 imagery downloaded** for all 13 cases (before/after, 4 bands each: True
  color, B04 red, B08 NIR, B11 SWIR) — 104 GeoTIFF files, geotag-verified.
- **NDVI/NDMI computed** (`scripts/compute_ndvi_ndmi.py`). Cloud-contamination check
  (manual visual) found: 3/13 reliable, 2/13 light caveat, 3/13 medium caveat,
  5/13 unreliable (heavy cloud — need redownload).
- **Permit baseline**: 4,608 IUP/IUPK polygons from BIG (Badan Informasi Geospasial)
  KSP SatuPeta — free, public, but a ~2022 snapshot (official MOMI/MODI APIs are
  currently down/login-gated, not real-time).
- **Cross-check demo**: NDVI-loss polygons overlaid against permit polygons for the
  3 reliable cases, using geopandas locally (not a managed database).
- **Training dataset corpus assembled (~3.9GB)**: MineNetCD256, Tang & Werner, Jasansky,
  Maus v2, ESA WorldCover, Hansen GFC, OSCD100, CloudSEN12+. The 13 ground-truth cases
  are repositioned as a **test/validation set**, not training data (too few samples).

## Huawei Cloud usage — CORRECTED

Only **2 Huawei Cloud services are actually used**:
- **ECS** (compute) — runs the imagery download, cloud QC, and NDVI/NDMI pipeline.
- **OBS** (object storage) — stores the raw Sentinel-2 GeoTIFFs.

Everything else is **our own resources / self-built**, not Huawei services:
- AI model training & inference (U-Net/DeepLabV3+) — own compute, not ModelArts.
- Geospatial cross-check — geopandas locally, not GaussDB.
- Backend API — self-built, not Huawei API Gateway.
- Web dashboard — self-built, not Astro.
- Alerting — self-built (email/webhook), not SMN.

> Open item: an earlier doc version (14 Nov) listed ModelArts as a 3rd finalized Huawei
> service alongside ECS/OBS. The latest instruction says it's ECS+OBS only — this still
> needs the team to confirm which is correct before it goes in the final pitch deck.

## Not done yet
- Actual trained change-detection model — datasets are assembled, training hasn't run
  (no GPU in the current dev environment).
- Redownload 5 cloud-contaminated locations with cleaner dates.
- Missing B02 (blue) band — needed for a proper BSI (bare-soil index); currently using
  NDMI as a rough proxy.
- Backend API + web dashboard — not built yet, planned next.
- Huawei Cloud account/credits — pending approval.

## Caveats to keep honest (don't overclaim)
- Permit data baseline is a ~2022 snapshot, not current — can miss 2023-2026 cases/status.
- Current NDVI cross-check is a simple threshold demo, not the trained AI model yet.
- AI output is designed to be **"flagged for review"**, not an automatic legal verdict —
  a human analyst reviews before any alert goes out.
