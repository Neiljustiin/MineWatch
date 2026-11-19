# MineWatch Web Dashboard — Rencana Pembangunan (MVP Demo)

Status: draft rencana, belum ada kode dibangun. Disusun 17 Nov 2026 berdasarkan kode
dan keputusan arsitektur yang SUDAH ADA di repo (`scripts/inference_pipeline.py`,
`scripts/permit_crosscheck.py`, `docs/KONTEKS_LENGKAP.md` Bagian 14-15), bukan asumsi baru.

## 0. Keputusan scope (dikonfirmasi user, 17 Nov 2026)
- **Scope**: MVP demo kompetisi — cukup untuk requirement "visual demo page" Huawei ICT
  Preliminary (Presentation Format). BUKAN produk live jangka panjang (auto-ingest
  Sentinel-2 tiap 5 hari) — itu di luar scope dokumen ini.
- **Cakupan data**: 13 ground-truth case locations yang sudah ada (bukan live pipeline).
- **Developer**: anggota tim lain (kemungkinan Rafi), bukan dieksekusi langsung oleh
  assistant — dokumen ini rancangan + skeleton, bukan implementasi penuh.
- **Hosting**: development lokal dulu, deploy ke Huawei ECS belakangan (instance belum
  diprovision — jangan desain yang butuh ECS utk development, hanya utk deploy akhir).
- **Auth**: TIDAK ada login di versi ini — view-only. Role admin/analyst didesain tapi
  TIDAK diimplementasi sampai ada keputusan scope lanjutan.

## 1. Kenapa precompute, bukan live inference per-request
Model masih training (v2 = IoU 0,411/F1 0,582 di test split MineNetCD256, v3/v4 masih
jalan — lihat `KONTEKS_LENGKAP.md` Bagian 15.1-15.2). Performa di domain Sentinel-2
Indonesia BELUM diukur (beda domain dari metrik evaluate.py). Jadi:
- Dashboard MVP menampilkan hasil **precomputed** (dijalankan sekali per case lewat
  `scripts/inference_pipeline.py` + `scripts/permit_crosscheck.py`, hasil disimpan
  sebagai file statis), BUKAN inference on-demand tiap kali halaman dibuka.
- **Satu titik integrasi** untuk ganti checkpoint pas v3/v4 selesai: cuma ganti
  `--checkpoint` path di script precompute, lalu re-run. Tidak ada perubahan kode
  dashboard/frontend sama sekali. Ini yang bikin "begitu training selesai bisa segera
  integrasi" — integrasinya adalah re-run 1 script, bukan rewrite dashboard.
- Tidak perlu database managed (konsisten dengan keputusan arsitektur: no GaussDB).
  13 kasus x beberapa KB JSON = file statis saja sudah cukup untuk MVP.

## 2. Stack yang direkomendasikan

**Backend: FastAPI (Python)**
**Frontend: HTML/CSS/JS statis + Leaflet.js** (tanpa React/Node build step)

Alasan (bukan pilihan default, ini justifikasi konkret):
1. Semua pipeline inti (`inference_pipeline.py`, `permit_crosscheck.py`, `model.py`)
   sudah Python — FastAPI bisa `import` langsung modul-modul itu, nol lapisan
   translasi/rewrite ke bahasa lain.
2. Leaflet gratis, tanpa API key, tanpa biaya (basemap OSM) — konsisten dengan prinsip
   proyek "self-built, bukan layanan berbayar" untuk komponen di luar ECS/OBS.
3. Tanpa toolchain Node/React berarti tanpa `npm install`, tanpa build step — developer
   tunggal (Rafi) bisa langsung `uvicorn main:app` dan buka browser, minim overhead
   setup di laptop/lab sendiri.
4. Satu proses (FastAPI serve API + static files sekaligus) → gampang dipindah ke 1
   ECS instance nanti (`uvicorn` di belakang `systemd`, atau 1 container Docker) —
   tidak perlu infra terpisah utk frontend vs backend.

**Alternatif yang DITOLAK dan kenapa**: Streamlit/Dash lebih cepat dibikin tapi kontrol
layout peta interaktif (multi-layer toggle, before/after slider) lebih terbatas
dibanding Leaflet native — untuk "visual demo page" yang dinilai juri, kontrol
visual lebih penting dari kecepatan development di sini. Kalau Rafi under waktu
sangat ketat, Streamlit + `streamlit-folium` adalah fallback valid, tapi FastAPI+Leaflet
tetap rekomendasi utama.

## 3. Struktur data (field EXACT dari kode, bukan rekaan)

Precompute script (baru, lihat §5) memanggil `crosscheck()` dan `run_pipeline()` yang
sudah ada, menghasilkan 1 JSON bundle per case:

```json
{
  "case": "kembar_emas_sultra",
  "name": "PT Kembar Emas Sultra (PT KES)",
  "data_quality_tier": "reliable",          // reliable | light_caveat | medium_caveat | unreliable
  "total_disturbed_area_ha": 0.0,
  "total_overlap_with_any_permit_ha": 0.0,
  "outside_all_nearby_permits_ha": 0.0,
  "pct_outside_any_permit": 0.0,
  "n_permits_found_nearby": 0,
  "permit_overlap_detail": [
    {"permit_name": "...", "commodity": "...", "issuer": "...", "status_code": "...",
     "permit_area_ha": 0.0, "overlap_with_disturbance_ha": 0.0,
     "pct_disturbance_inside_this_permit": 0.0, "distance_km_from_disturbance_centroid": 0.0}
  ],
  "disturbance_geojson_path": "data/<case>/disturbance.geojson",
  "before_image_path": "data/<case>/before_preview.png",
  "after_image_path": "data/<case>/after_preview.png",
  "model_meta": {
    "checkpoint": "production_v2_base64", "base_ch": 64, "epoch": 12,
    "threshold": 0.5,
    "eval_disclaimer": "IoU 0.411 / F1 0.582 diukur di test split MineNetCD256, BELUM divalidasi di domain Sentinel-2 Indonesia."
  }
}
```

`data_quality_tier` memakai klasifikasi yang SUDAH ADA dari QA tim (reliable/light
caveat/medium caveat/unreliable, lihat `analysis/ndvi_ndmi/HASIL_NDVI_NDMI.md`) — jangan
bikin skema badge baru.

**TIDAK ADA field `is_illegal`/vonis** di skema ini — sengaja, konsisten dengan prinsip
proyek. UI wajib menampilkan hasil sebagai "flagged for review", bukan status hukum.

## 4. Halaman & fitur (MVP)

### 4.1 Halaman daftar kasus (`/`)
- Grid/list 13 kasus. Per kartu: nama, provinsi, badge `data_quality_tier`, ringkasan
  (`total_disturbed_area_ha`, `pct_outside_any_permit`), thumbnail citra after.
- Filter sederhana: by provinsi, by `data_quality_tier`, sort by luas area/persentase.
- Banner disclaimer permanen di header: *"Hasil bersifat flagged for review — bukan
  vonis hukum otomatis. Memerlukan verifikasi analis."*

### 4.2 Halaman detail kasus (`/case/<id>`)
- **Peta interaktif (Leaflet)**: basemap OSM, layer toggle before/after (opacity
  slider, BUKAN time-series — cuma 2 titik waktu sesuai data yang ada), layer polygon
  gangguan terdeteksi (warna netral, bukan hijau/merah), layer polygon izin nearby
  (dari `permit_overlap_detail`, popup per-polygon berisi nama/komoditas/status).
- **Panel statistik**: tabel `total_disturbed_area_ha`, `overlap_ha`, `outside_ha`,
  `pct_outside_any_permit`, `n_permits_found_nearby`.
- **Tabel izin nearby**: semua baris `permit_overlap_detail`, sortable.
- **Panel metadata model**: checkpoint/epoch/threshold + `eval_disclaimer` eksplisit
  ditampilkan, bukan disembunyikan di footer kecil.
- **Badge data quality** dengan tooltip penjelasan (mis. "medium caveat: awan parsial
  pada citra after, lihat QA log").

### 4.3 Halaman metodologi (`/about`) — opsional tapi direkomendasikan
Ringkasan 1 halaman alur pipeline (citra → model → cross-check → flagged for review)
+ link ke `docs/REFERENCES.md` untuk dasar pustaka. Berguna buat juri kompetisi yang
mau ngecek metodologi tanpa baca repo penuh.

## 5. Yang TIDAK dibangun di MVP ini (sengaja, out-of-scope)
- Login/role admin-analyst (didesain kontraknya di §3 lewat `data_quality_tier`, tapi
  implementasi auth ditunda — keputusan user eksplisit view-only dulu).
- Live ingest Sentinel-2 otomatis tiap 5 hari.
- Alerting email/webhook.
- Export laporan PDF.
- Time-series slider lebih dari 2 titik waktu (before/after) — data yang ada memang
  cuma sepasang per kasus.

## 6. Struktur folder yang diusulkan
```
dashboard/
  backend/
    main.py                 # FastAPI app: GET /api/cases, GET /api/cases/{id}
    static/                 # build precompute dari sini di-serve
  frontend/
    index.html               # daftar kasus
    case.html                 # detail + peta Leaflet
    js/map.js, js/list.js
    css/style.css
  data/
    <case_name>/
      bundle.json            # schema di §3
      disturbance.geojson
      before_preview.png
      after_preview.png
scripts/
  export_dashboard_bundle.py  # BARU — panggil inference_pipeline.run_pipeline()
                               # + crosscheck(), tulis dashboard/data/<case>/bundle.json
                               # Titik integrasi tunggal saat ganti checkpoint v3/v4.
```

## 7. Urutan kerja yang disarankan untuk Rafi
1. Tulis `scripts/export_dashboard_bundle.py` — loop 13 case, panggil pipeline yang
   sudah ada, tulis `bundle.json` + PNG preview + GeoJSON ke `dashboard/data/`.
   **Tidak perlu GPU devbox** kalau checkpoint v2 sudah ada di disk — ini cuma re-run
   inference existing, bukan training baru.
2. Backend FastAPI: 2 endpoint saja (`GET /api/cases` list ringkas, `GET /api/cases/{id}`
   detail penuh) yang baca `bundle.json`, tanpa DB.
3. Frontend: halaman list dulu (paling cepat validasi data benar), baru halaman detail
   dengan peta.
4. QA manual: buka tiap 13 kasus, cek angka cocok dengan `HASIL_NDVI_NDMI.md` dan
   `download_progress_log.md` — jangan percaya tampilan UI tanpa cross-check ke log asli.
5. Baru setelah semua jalan lokal: deploy ke 1 ECS instance (spec + region + biaya
   dibahas terpisah saat instance mau diprovision — belum sekarang).

## 8. Pertanyaan terbuka yang masih perlu dipastikan sebelum/selama development
- Apakah 10/13 kasus yang masih caveat/unreliable tetap ditampilkan dengan badge jujur,
  atau disembunyikan dari demo sampai redownload tuntas? (rekomendasi: tetap tampilkan
  dengan badge — konsisten dengan prinsip "jangan menutupi masalah data quality").
- Siapa yang pegang GeoTIFF before/after asli untuk di-convert ke preview PNG saat
  precompute — perlu dipastikan lokasinya ada di `data/sentinel2_pilot/` sesuai log.
- Apakah checkpoint v2 (`production_v2_base64`) yang dipakai untuk precompute pertama,
  atau nunggu v3/v4 dulu baru bikin bundle pertama? (rekomendasi: mulai dari v2 sekarang
  biar dashboard bisa divalidasi sambil nunggu v3/v4, lalu re-run `export_dashboard_bundle.py`
  begitu v3/v4 final — ini persis skenario "integrasi cepat" yang diminta).
