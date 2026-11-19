# MineWatch dashboard

Web dashboard untuk deteksi tambang ilegal (Huawei ICT Competition, entry MineWatch).
Desain mengacu ke `Main.dc.html` (overview) dan `Case.dc.html` (detail kasus), konteks di `context.md`.

Stack:
- `pipeline/`  Python (geopandas/rasterio) — precompute data dari repo `huawei-ict-illegal-mining` ke `data/`
- `backend/`   FastAPI + SQLite (keputusan analis, assignment, audit trail)
- `frontend/`  React + Vite + Leaflet, di-build ke `frontend/dist` dan disajikan oleh FastAPI

## Menjalankan

    # 1. (opsional) bangun ulang data dari repo analisis
    /usr/bin/python3 pipeline/build_data.py --repo /home/ubuntu/huawei-ict-illegal-mining

    # 2. build frontend (sekali, atau setiap ada perubahan di frontend/src)
    cd frontend && npm install && npm run build && cd ..

    # 3. jalankan server (dari root proyek) -> http://127.0.0.1:8000
    .venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Mode dev frontend (hot reload, proxy ke API :8000): `cd frontend && npm run dev` -> http://localhost:5173

Konfigurasi lewat env:
- `MINEWATCH_DATA`         direktori data (default `./data`)
- `MINEWATCH_STATUS_RULE`  `plurality` (default) atau `strict`
- `MINEWATCH_HIGH_PCT`     ambang % di luar izin untuk No Matching Permit pada rule `strict` (default 50). Nama lama `MINEWATCH_MERAH_PCT` tetap diterima.

## Data & kejujuran

- 13 kasus ground-truth pilot (`MW-GT-xx`), field disalin dari `docs/KONTEKS_LENGKAP.md` — tidak ada kasus karangan.
- Deteksi = threshold NDVI (dNDVI < -0.2) pada pasangan Sentinel-2 L2A, bukan model AI.
  Poligon loss dihitung ulang di grid penuh (min 25 px, sama dengan `inference_pipeline.mask_to_polygons`);
  untuk 3 kasus yang punya angka repo hasilnya cocok (551/553, 589/592, 373/374 ha).
- Before/after di-realign pada koordinat GeoTIFF (analisis asli me-resize extent yang beda).
- Kategori No Matching Permit, Permit Expired, dan Inside Valid Permit menjelaskan hasil pencocokan dengan data izin, bukan prioritas atau putusan legalitas. Aturannya masih provisional.
- MW-GT-04 (Kristalin): citra before berawan ~25-30%, sinyal ditandai tidak andal (`recheck_note`).
- Dispatch ke DLHK/Polda = MOCK. Keputusan dan audit tersimpan di `data/runtime/minewatch.db`, tidak ada yang dikirim.
- Basemap: Esri Dark Gray / World Imagery (butuh internet). Layer izin: BIG KSP ~2022, 4.608 poligon.

## API ringkas

    GET  /api/health | /api/meta | /api/cases | /api/cases/{id}
    POST /api/cases/{id}/decision   {decision, notes, ack, actor}
    POST /api/cases/{id}/recall     {actor}          (maks 10 menit)
    POST /api/cases/{id}/assign     {assignee, actor}
    GET  /api/cases/{id}/report     laporan HTML siap print/PDF
    GET  /api/permits?bbox=w,s,e,n | /api/permits/all | /api/permits/search?q=&prov=&page=
    GET  /api/export.geojson
