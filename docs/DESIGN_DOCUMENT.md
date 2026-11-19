# MineWatch — Technical Design Document

> **Dokumen ini BUKAN pengulangan Entry Information Form.** Tiap bagian dimulai
> dengan 1 baris pointer ke bagian Entry Form yang relevan (kalau ada), lalu
> LANGSUNG ke rincian teknis yang TIDAK ada di Entry Form. Kalau pembaca ingin
> narasi "kenapa ini penting / value bisnis", baca Entry Form — dokumen ini
> jawab "bagaimana cara kerjanya & bagaimana cara mereproduksinya".

**Alasan dokumen ini ada:** syarat resmi Huawei ICT Competition Innovation
Track — materi kode & desain yang disubmit harus *capable of reproducing the
effects demonstrated during the defense session*; kalau juri coba jalanin dan
hasilnya beda/gagal, tim berisiko didiskualifikasi dari babak lanjutan. Jadi
dokumen ini dioptimalkan untuk REPRODUCIBILITY, bukan storytelling.

---

## 0. Peta anti-duplikasi

| Topik | Entry Form | Design Document (dokumen ini) |
|---|---|---|
| Kenapa masalah ini penting, value bisnis | §1, §1.1–§1.2 (lengkap) | Tidak diulang — lihat Entry Form |
| Arsitektur sistem (level konsep) | §1 (naratif + 1 diagram) | §1 di sini: pemetaan modul → file kode persis |
| Dataset: nama, jumlah, sumber | §2.1 (ringkasan) | §2 di sini: skema kolom, split exact, **tabel QA 13 lokasi versi TERBARU** (Entry Form pakai angka basi) |
| Model: versi v1-v4, narasi kenapa berubah | §2.4 (naratif) | §3–§4 di sini: arsitektur layer-by-layer, command + hyperparameter EXACT tiap versi |
| Hasil akhir | §3 "Current achievements" (angka final) | §5 di sini: tabel lengkap semua versi + command evaluasi + cara reproduksi |
| Cross-check izin | §2.5 (naratif + excerpt pendek) | §6 di sini: signature fungsi lengkap, algoritma spatial-index |
| Dashboard | §1.1.3 (deskripsi UX state) | §7 di sini: desain API/endpoint, alur data precompute (tidak disinggung sama sekali di Entry Form) |
| Huawei Cloud | §1 (status "pending") | §8 di sini: spek target OBS/ECS + status provisioning jujur (konsisten, bukan kontradiksi) |

---

## 1. Peta modul → file kode

Diagram alur sudah ada di Entry Form §1 (Figure 1). Pemetaan konkret ke kode:

| Blok alur | File | Status |
|---|---|---|
| Akuisisi data (integrity check) | `scripts/download_data.py` | Implemented |
| Audit geometri izin (titik vs polygon) | `scripts/audit_permit_csv.py` | Implemented |
| Bangun patch training Indonesia (STAC) | `scripts/jasansky_stac_download.py`, `scripts/jasansky_build_patches.py` | Implemented |
| Loader dataset (Arrow-based) | `scripts/dataset_loader.py` | Implemented |
| Arsitektur model | `scripts/model.py` | Implemented |
| Training loop produksi | `scripts/train_production.py` | Implemented |
| Evaluasi | `scripts/evaluate.py` | Implemented |
| Inference end-to-end | `scripts/inference_pipeline.py` | Implemented |
| Cross-check izin | `scripts/permit_crosscheck.py` | Implemented |
| Sampling negative patches | `scripts/sample_negative_locations.py`, `scripts/fetch_negative_patches.py` | Implemented |
| Dashboard backend/frontend | `dashboard-huawei/` (repo terpisah) | Implemented (lokal) |
| Huawei Cloud OBS/ECS deployment | — | **Belum diprovisioning** — lihat §8 |

---

## 2. Dataset & preprocessing — rincian

### 2.1 Sumber & ukuran (exact)
- `data/training_datasets/minenetcd256/` — dataset utama (format Arrow), benchmark publik MineNetCD.
- `data/training_datasets/jasansky_patches/` — 25 tile Indonesia-spesifik, diambil via STAC
  (`jasansky_stac_download.py`), dipecah train/val oleh `jasansky_build_patches.py --val-frac`.
- `data/training_datasets/negative_patches/` — patch negatif (area tanpa perubahan), dari
  `sample_negative_locations.py` + `fetch_negative_patches.py`, dipakai lewat flag
  `MINEWATCH_INCLUDE_NEGATIVES=1` saat training (mengurangi false-positive rate, belum tervalidasi di v4).

### 2.2 Tabel QA 13 lokasi ground-truth — VERSI TERBARU (14 Nov 2026)
> Entry Form §2.1.1 masih pakai angka lama ("3 reliable, 5 caveat, 5 unreliable").
> Setelah redownload 14 Nov 2026, **0 lokasi unreliable tersisa**. Ini angka yang benar:

| Tier | Jumlah | Lokasi |
|---|---|---|
| ✅ Reliable | 6 | Kembar Emas Sultra, DAS Kampak (Bangka Barat), Laroenai (Morowali), Dusun Nadi (Bangka Tengah), Daya Sumber Mining Indonesia, Singlurus Pratama |
| ⚠️ Caveat ringan | 2 | Pangkalan Jambu, Air Liki (Jambi) |
| ⚠️⚠️ Caveat sedang | 3 | Masempo Dalle (Konawe Utara), Bumi Morowali Utama, Muara Hemat (Jambi) |
| ⚠️ Caveat (redownload, masih ada artefak) | 2 | Asmin Koalindo Tuhup (awan residual), Kristalin Eka Lestari Papua (artefak resize-mismatch, bukan deforestasi) |
| ❌ Unreliable | **0** | — |

Sumber lengkap + metodologi NDVI/NDMI per lokasi: `analysis/ndvi_ndmi/HASIL_NDVI_NDMI.md`
dan `analysis/ndvi_ndmi/ndvi_ndmi_results.json`.

### 2.3 Keterbatasan data yang harus diungkap ke juri (jujur, bukan disembunyikan)
- Band B02 (Blue) tidak pernah didownload → BSI standar (Rikimaru) tidak bisa dihitung,
  dipakai NDMI sebagai proksi. Didokumentasikan, bukan ditutupi.
- Redownload kadang menghasilkan resolusi piksel berbeda dari file lama (zoom level beda) →
  `compute_ndvi_ndmi.py` resize nearest-neighbor ke ukuran terkecil sebelum delta piksel —
  approksimasi kasar, bisa memicu artefak kalau extent crop before/after sedikit bergeser
  (kasus: Kristalin Eka Lestari Papua).
- Preview viewport Copernicus Browser **tidak bisa dipercaya** untuk menilai cloud coverage —
  satu-satunya cara valid: download penuh → convert PNG res penuh → `vision_analyze` manual.

---

## 3. Arsitektur model — spesifikasi exact

**FC-Siam-diff** (Daudt, Le Saux, Boulch 2018, ICIP, arXiv:1810.08462) — dipilih karena
arsitektur published & tervalidasi untuk "2 citra (before/after) → mask perubahan", bukan
arsitektur hasil tebakan sendiri (`scripts/model.py`).

- 1 encoder (bobot SHARED) meng-encode imageA & imageB terpisah → feature pyramid per gambar.
- Tiap level resolusi: `|featureA − featureB|` (absolute difference) sebagai sinyal "seberapa beda".
- Decoder (mirip U-Net) naikin resolusi bertahap, gabungin sinyal diff tiap level (skip
  connection), keluarin 1 channel logit per pixel (256×256) = peta probabilitas perubahan.
- `base_ch` adalah parameter utama kapasitas model — dipakai buat progresi v1→v4 (lihat §4).

---

## 4. Konfigurasi training — command & hyperparameter EXACT per versi

| Versi | `base_ch` | Loss | Regularisasi | Data | Command inti |
|---|---|---|---|---|---|
| v1 | 32 | default (baseline) | tidak ada | MineNetCD256 saja | `python3 train_production.py --base-ch 32 --epochs 50 --batch-size 8` |
| v2 | 64 | sama dgn v1 | tidak ada | MineNetCD256 saja | `python3 train_production.py --base-ch 64 --epochs 50 --batch-size 8` |
| v3 | 64 | Focal-Dice (0.5/0.5) | dropout 0.3, weight decay, augmentasi fotometrik | MineNetCD256 saja | `python3 train_production.py --base-ch 64 --dropout 0.3 --loss focal_dice --epochs 50 --batch-size 8` |
| v4 | 64 | Focal-Dice (0.5/0.5) | sama dgn v3 | + 25 tile Jasansky (Indonesia, via STAC) | `MINEWATCH_INCLUDE_JASANSKY=1 python3 train_production.py --base-ch 64 --dropout 0.3 --loss focal_dice --epochs 50 --batch-size 8` |
| v5a | 64 | Tversky (α0.7/β0.3) | dropout 0.3, EMA 0.999, cosine warmup 2 epoch, **dari scratch** | + Jasansky + negative patches | `MINEWATCH_INCLUDE_JASANSKY=1 MINEWATCH_INCLUDE_NEGATIVES=1 python3 train_production.py --base-ch 64 --epochs 50 --batch-size 8 --dropout 0.3 --loss tversky --tversky-alpha 0.7 --tversky-beta 0.3 --scheduler cosine --warmup-epochs 2 --ema-decay 0.999 --patience 12` (run_name: `production_v5_tversky07_negatives`) |
| v5b (dipakai) | 64 | Tversky (α0.7/β0.3) | dropout 0.3, EMA 0.999, cosine warmup 2 epoch, **fine-tune dari checkpoint v4** (`init_from: checkpoints/production_v4_base64_reg_jasansky/best_model.pt`), lr 1e-4 (bukan 3e-4) | + Jasansky (tanpa negative patches) | `python3 train_production.py --base-ch 64 --dropout 0.3 --loss tversky --tversky-alpha 0.7 --tversky-beta 0.3 --scheduler cosine --warmup-epochs 2 --ema-decay 0.999 --patience 12 --lr 0.0001 --init-from checkpoints/production_v4_base64_reg_jasansky/best_model.pt` (run_name: `production_v5_finetune_tversky`) |

> **Status v5 (MEASURED, 19 Nov 2026, diverifikasi langsung dari log lab di `/tmp/eval_v5*.log`
> dan `/tmp/eval_v5_finetune*.log` via SSH container `172.20.0.160`):** dua varian dicoba.
> **v5a (dari scratch + negative patches) kalah di SEMUA split** dibanding v4 (test IoU 0.411
> vs 0.438; Indonesia IoU 0.233 vs 0.360) — **tidak dipakai**. **v5b (fine-tune dari v4, tanpa
> negative patches) menang di split Indonesia** (IoU 0.384 vs 0.360, F1 0.555 vs 0.530, precision
> 0.625) tapi sedikit kalah di split test global (IoU 0.414 vs 0.438) — trade-off recall→precision
> (recall 0.500), cocok buat workflow "kurangi false positive ke antrian analis". **Dashboard masih
> jalanin checkpoint v4** — promosi ke v5b butuh re-run export 13 kasus, BELUM dilakukan.

Teknik training (semua versi, implementasi di `train_production.py`):
mixed precision (AMP, autocast+GradScaler — RTX 3060 Ampere tensor core), `pin_memory=True`,
checkpointing berdasar **val loss** (bukan train loss — mencegah overfit lolos ke-save),
early stopping dgn `patience`, LR scheduler `ReduceLROnPlateau` (v1-v2) / cosine warmup (v3+).

---

## 5. Protokol evaluasi & hasil terukur

Command: `python3 evaluate.py --checkpoint <path/best_model.pt> --split <test|jasansky_val>`

| Versi | Split `test` IoU / F1 / Precision / Recall | Split `jasansky_val` IoU / F1 / Precision / Recall |
|---|---|---|
| v1 | 0.383 / 0.554 / — / — | N/A (belum dievaluasi di split ini) |
| v2 | 0.411 / 0.582 / — / — | 0.112 / 0.202 / — / — |
| v3 | 0.430 / 0.602 / — / — | 0.175 / 0.297 / — / — |
| v4 (dipakai dashboard) | **0.438 / 0.609** / — / — | **0.360 / 0.530** / — / — |
| v5a (dari scratch, TIDAK dipakai) | 0.411 / 0.582 / 0.542 / 0.629 | 0.233 / 0.378 / 0.328 / 0.446 |
| v5b (fine-tune dari v4) | 0.414 / 0.585 / 0.638 / 0.540 *(full test set, 19.355 patch)* | **0.384 / 0.555 / 0.625 / 0.500** |

Checkpoint yang dipakai dashboard saat ini (TIDAK berubah): `checkpoints/production_v4_base64_reg_jasansky/best_model.pt`.
Checkpoint v5b (belum dipromosikan ke dashboard): `checkpoints/production_v5_finetune_tversky/best_model.pt` (lab, belum disinkron ke repo lokal/`/home/ubuntu`).

> Sel "—" pada precision/recall v1-v4 = angka itu tidak pernah dicatat terpisah saat run asli
> (cuma IoU/F1 yang dilaporkan ke Entry Form) — bukan nol, cuma belum ada datanya. Jangan diisi
> tebakan kalau dibutuhkan, re-run `evaluate.py` di checkpoint tersimpan untuk ambil angkanya.

---

## 6. Pipeline inference & cross-check izin — rincian algoritmik

`inference_pipeline.py`: tiling paired GeoTIFF → 256×256 input → jalanin checkpoint →
restore spatial output → vektorisasi mask → panggil `permit_crosscheck.crosscheck()`.

`permit_crosscheck.py` (reusable, dipanggil dashboard maupun analisis manual):
- Load semua `data/big_satupeta_iup/iup_part_*.geojson` → 1 GeoDataFrame, di-cache in-memory
  (load berat, jangan diulang tiap panggilan).
- Luas area: **geodesic** via `pyproj.Geod(ellps="WGS84")` — akurat di mana pun di Indonesia
  tanpa perlu pilih UTM zone manual (beda dari pendekatan proyeksi-tetap yang umum dipakai).
- Jarak: geodesic km (`Geod.inv`), bukan "distance_deg" (derajat lat/lon bukan satuan jarak
  konsisten — bug di versi lama).
- Pencarian permit "nearby": spatial index pakai bounding-box filter dulu, baru polygon-exact
  check — supaya efisien dipanggil berkali-kali tanpa scan ribuan polygon tiap kali.
- **Prinsip desain (wajib dipertahankan)**: output SELALU `"flagged for review"` — overlap %
  dan area di luar izin BUKAN vonis otomatis "ilegal", cuma sinyal untuk analis manusia.
  Tidak ada field `is_illegal` di mana pun dalam sistem.

---

## 7. Desain backend/dashboard — tidak dibahas di Entry Form

Stack: FastAPI (backend) + React + Vite + Leaflet (frontend), repo terpisah `dashboard-huawei/`.

Alur data (precompute, bukan live inference):
1. `inference_pipeline.py` dijalankan offline untuk 13 lokasi ground-truth dengan checkpoint v4.
2. Hasil (polygon kandidat, overlap izin, metadata model) di-export jadi JSON statis.
3. Backend FastAPI serve JSON itu ke frontend — bukan menjalankan model secara live per-request.
4. Integrasi checkpoint baru: re-run step 1-2 dengan checkpoint baru, tanpa ubah kode dashboard.

Endpoint utama (perlu didaftar presisi sebelum submission, draft):
- `GET /api/cases` — daftar 13 lokasi + tier QA + ringkasan statistik
- `GET /api/cases/{id}` — detail 1 lokasi: polygon, overlap table, metadata checkpoint/threshold
- (Perlu dikonfirmasi ke pemilik repo dashboard — path exact & skema response belum di-audit di
  sesi ini, **jangan ditulis seolah final** sebelum dicek langsung ke kode.)

---

## 8. Infrastruktur Huawei Cloud — status jujur

Konsisten dengan Entry Form (§1): "Huawei Cloud deployment evidence is pending" — bukan
kontradiksi, tapi dirinci:

| Komponen | Peran rencana | Status |
|---|---|---|
| OBS (Object Storage Service) | Simpan citra satelit, checkpoint model, hasil export (versioned) | **Belum diprovisioning** |
| ECS (Elastic Compute Service) | Hosting dashboard + API, jalanin inference pipeline 24 jam | **Belum diprovisioning** |
| ModelArts | Training skala besar (kondisional, roadmap) | Belum — training saat ini di GPU lab lokal (RTX 3060) |

Rate card yang dipakai utk costing (Entry Form §1.2.1): OBS Standard storage USD 0.023/GB-bulan,
ECS pay-per-use USD 0.15/jam (s6.xlarge.2, region AP-Singapore) — angka ini publikasi resmi
Huawei Cloud, **bukan hasil provisioning nyata**.

---

## 9. Cara mereproduksi hasil yang didemoin (WAJIB ada sebelum submission final)

Urutan command persis dari lingkungan bersih sampai hasil yang ditampilkan di demo:

```
# 1. Setup environment
cd huawei-ict-illegal-mining
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt   # [TODO: pastikan file ini ada & lengkap]

# 2. Siapkan dataset (path exact, lihat §2.1)
#    data/training_datasets/minenetcd256/, jasansky_patches/, negative_patches/

# 3. Training (v4, konfigurasi final yang dipakai dashboard)
MINEWATCH_INCLUDE_JASANSKY=1 python3 scripts/train_production.py \
  --base-ch 64 --dropout 0.3 --loss focal_dice --epochs 50 --batch-size 8

# 4. Evaluasi
python3 scripts/evaluate.py --checkpoint checkpoints/production_v4_base64_reg_jasansky/best_model.pt --split test
python3 scripts/evaluate.py --checkpoint checkpoints/production_v4_base64_reg_jasansky/best_model.pt --split jasansky_val

# 5. Inference + cross-check (per lokasi ground-truth)
python3 scripts/inference_pipeline.py --checkpoint checkpoints/production_v4_base64_reg_jasansky/best_model.pt --case <id>
```

> **[TODO sebelum submission]**: verifikasi tiap command di atas benar-benar jalan dari
> environment bersih (bukan cuma dari memori/catatan), cek `requirements.txt` ada & versi
> pinned, dan tempelkan checksum/hash checkpoint yang dipakai supaya juri bisa konfirmasi
> file yang disubmit = file yang menghasilkan demo.

---

## 10. Keterbatasan yang diungkap ke juri (jujur, bukan ditutupi)

- Precision/recall belum dioptimalkan untuk production — v4 masih 0.609 F1 di split `test`,
  turun ke 0.530 di `jasansky_val` (domain gap citra Indonesia vs benchmark global).
- Model belum divalidasi untuk operasi tambang bawah tanah atau dredge individual — scope
  rilis pertama cuma candidate land change (sesuai Entry Form §1.1).
- Radiometric QA untuk raster lama (negative reflectance, provider offset) masih open item
  — lihat Entry Form §2.1.1, belum diselesaikan di sesi ini.
- Endpoint dashboard API (§7) belum diaudit presisi — perlu konfirmasi ke kode repo
  `dashboard-huawei` sebelum dicantumkan sebagai final di submission.
- v5 belum final (lihat §4) — jangan submit angka v5 kecuali sudah dikonfirmasi dari log run.

---

## 11. Inventaris file kode (untuk bundel "code files" submission)

| File | Peran |
|---|---|
| `scripts/model.py` | Arsitektur FC-Siam-diff |
| `scripts/train_production.py` | Training loop produksi (AMP, checkpointing, early stopping) |
| `scripts/dataset_loader.py` | Arrow-based dataset loader |
| `scripts/evaluate.py` | Evaluasi checkpoint vs split |
| `scripts/inference_pipeline.py` | Inference end-to-end + panggil cross-check |
| `scripts/permit_crosscheck.py` | Cross-check polygon kandidat vs izin resmi (geodesic) |
| `scripts/jasansky_stac_download.py`, `jasansky_build_patches.py` | Akuisisi + bangun patch training Indonesia via STAC |
| `scripts/sample_negative_locations.py`, `fetch_negative_patches.py` | Sampling & fetch patch negatif |
| `scripts/download_data.py` | Integrity-check akuisisi dataset publik |
| `scripts/audit_permit_csv.py` | Audit geometri izin (titik vs polygon) |
| `scripts/compute_ndvi_ndmi.py` | Analisis NDVI/NDMI 13 lokasi ground-truth (bukti kuantitatif pilot) |

---

*Dokumen ini draft awal — bagian bertanda [TODO] wajib diselesaikan/diverifikasi sebelum
file ini ikut disubmit sebagai bagian materi babak preliminary.*
