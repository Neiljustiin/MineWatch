# Hasil Hitung NDVI/NDMI — 13 Lokasi Pilot MineWatch

Tanggal analisis: 14 November 2026
Script: `scripts/compute_ndvi_ndmi.py` (Python 3.10 + numpy + PIL + matplotlib)
Data JSON lengkap: `analysis/ndvi_ndmi/ndvi_ndmi_results.json`
Visualisasi (before RGB | after RGB | NDVI delta heatmap): `analysis/ndvi_ndmi/*.png`

## Metodologi

- **NDVI** = (B08 − B04) / (B08 + B04) — indeks vegetasi standar.
- **NDMI** = (B08 − B11) / (B08 + B11) — proxy kelembaban/bare-soil, dipakai
  sebagai pengganti BSI standar karena **band B02 (Blue) tidak didownload**
  di sesi sebelumnya (cuma True color RGB + B04 + B08 + B11), jadi BSI
  Rikimaru (butuh Blue) tidak bisa dihitung persis. Ini trade-off yang
  didokumentasikan, bukan disembunyikan — kalau mau BSI asli, band B02 harus
  didownload ulang untuk semua 13 lokasi.
- **Metrik utama yang dipakai: "sharp NDVI loss pixel fraction"** = persentase
  piksel yang NDVI-nya turun >0.2 dari before ke after. Ini LEBIH ANDAL
  daripada rata-rata NDVI satu frame penuh, karena area tambang biasanya cuma
  sebagian kecil dari frame (1491×835 px) — rata-rata frame gampang
  "tenggelam" oleh variasi musiman vegetasi di sekitarnya atau kesalahan
  akibat awan.

## TEMUAN PENTING: Verifikasi tag TIFF + extrema pixel TIDAK CUKUP

Sebelumnya tiap lokasi "dinyatakan sehat" kalau tag GeoTIFF (33550/33922) ada
dan extrema pixel bukan nodata murni (bukan semua 0). Ternyata itu nggak
nangkep **kontaminasi awan** — piksel awan punya reflektansi tinggi (bukan 0),
jadi lolos cek otomatis tapi tetap merusak NDVI (awan = piksel terang +
near-infrared mirip, NDVI jadi mendekati 0, meniru pola "tanah gundul").

Setelah cross-check visual manual (vision_analyze) ke semua 13 pasang
before/after, ditemukan:

### ✅ RELIABLE (3 lokasi) — awan minimal/tidak ada, NDVI delta valid
| Lokasi | NDVI mean Δ | Sharp loss (piksel) | Catatan |
|---|---|---|---|
| Kembar Emas Sultra | −0.122 | 22.4% | Area merah (NDVI delta) persis bertumpuk sama area tambang terbuka yang terlihat jelas di citra after — **tervalidasi visual** |
| DAS Kampak, Bangka Barat | −0.029 | 12.8% | Citra bersih, sungai & kolam tambang timah jelas |
| Laroenai, Morowali | +0.049 | 15.9% | Mostly bersih (sedikit awan sudut kiri-bawah), area tambang nikel pesisir jelas meluas |

### ⚠️ CAVEAT RINGAN (2 lokasi) — sedikit awan di sudut, inti area masih valid
| Lokasi | NDVI mean Δ | Sharp loss (piksel) | Catatan |
|---|---|---|---|
| Pangkalan Jambu | +0.036 | 4.6% | Awan kecil di sudut, area sungai/sawah jelas |
| Air Liki, Jambi | +0.180 | 3.1% | Awan kecil di sudut + sedikit haze, pola sungai & jalan tambang jelas |

### ⚠️⚠️ CAVEAT SEDANG (3 lokasi) — awan parsial, interpretasi hati-hati
| Lokasi | NDVI mean Δ | Sharp loss (piksel) | Catatan |
|---|---|---|---|
| Masempo Dalle, Konawe Utara | −0.018 | 22.5% | Awan di sudut before & after, area sawah/kebun inti masih kelihatan |
| Bumi Morowali Utama | +0.028 | 14.3% | Awan sedang di before, area tambang oranye masih kelihatan di keduanya |
| Muara Hemat, Jambi | −0.087 | 14.0% | Awan tersebar di after — **patch merah NDVI delta kemungkinan sebagian bayangan awan, bukan murni deforestasi** |

### ❌ UNRELIABLE — STATUS LAMA (sudah diperbaiki, lihat update di bawah)
5 lokasi awalnya tertutup awan tebal: Asmin Koalindo Tuhup, Dusun Nadi,
Daya Sumber Mining Indonesia, Singlurus Pratama, Kristalin Eka Lestari Papua.
Semua sudah **didownload ulang** (14 Nov 2026) dengan tanggal baru, dicari
dengan iterasi mundur manual + verifikasi full-frame (bukan cuma viewport).

### 🔄 UPDATE 14 Nov 2026 — hasil redownload 5 lokasi unreliable
| Lokasi | Before baru | After baru | NDVI Δ (baru) | Sharp loss (px) | Status setelah redownload |
|---|---|---|---|---|---|
| Asmin Koalindo Tuhup | 2022-03-26 (ganti dari 2019-06-30) | 2025-06-23 (tetap, sudah OK) | +0.083 | 14.2% | ⚠️ CAVEAT SEDANG — awan tersebar msh ada di kedua frame (~15-20%), cluster merah NDVI delta di sisi kanan citra berkorelasi dgn posisi awan, bukan murni deforestasi. Jauh lebih baik dari sebelumnya (awan solid >50%) |
| Dusun Nadi, Bangka Tengah | 2019-04-25 (ganti dari 2019-06-29) | 2026-08-11 (ganti dari 2026-08-31) | +0.060 | 17.4% | ✅ RELIABLE — awan jauh berkurang, area tambang pesisir jelas di kedua frame, delta merah berkorelasi dgn ekspansi tambang asli |
| Daya Sumber Mining Indonesia | 2023-09-28 (ganti dari sebelumnya) | 2026-10-07 (ganti dari sebelumnya) | +0.032 | 12.0% | ✅ RELIABLE — kedua frame mayoritas bersih, cluster merah NDVI delta persis bertumpuk area tambang yang meluas (tan patch baru di after) |
| Singlurus Pratama | 2020-01-23 (ganti dari 2020-06-16) | 2024-04-16 (ganti dari 2026-11-04) | +0.017 | 19.9% | ✅ RELIABLE — pita awan diagonal minor di before tapi tidak menutupi area tambang; ekspansi tambang jelas terlihat di after, delta merah berkorelasi dgn area yang berubah jadi terbuka |
| Kristalin Eka Lestari, Papua | 2018-09-19 (dicek ulang, TIDAK diganti — sudah OK) | 2026-08-18 (ganti dari 2026-08-25) | −0.058 | 24.0% | ⚠️ CAVEAT — **artefak baru ditemukan**: blok merah besar di pojok kiri-atas NDVI delta BUKAN deforestasi, melainkan mismatch garis pantai/laut vs darat akibat before & after punya extent/crop pixel yang sedikit berbeda (1491×835 vs 2500×1400, di-resize paksa ke ukuran sama untuk perbandingan piksel-per-piksel — lihat keterbatasan teknis di bawah). Sinyal di bagian tengah-kanan (area permukiman/tambang) tetap valid. |

**Keterbatasan teknis baru yang ditemukan & diperbaiki sebagian:**
- Redownload kadang menghasilkan resolusi piksel berbeda dari file lama
  (karena zoom level berbeda saat browsing ulang) — before/after bisa beda
  shape (contoh: 2500×1400 vs 1491×835 vs 1261×1670). Script
  `compute_ndvi_ndmi.py` di-patch untuk resize otomatis (nearest-neighbor,
  bukan reproject geospasial presisi) ke ukuran terkecil sebelum hitung
  delta piksel-per-piksel. Ini approksimasi kasar — kalau extent crop before
  vs after juga sedikit bergeser (bukan cuma beda resolusi), bisa muncul
  artefak false-positive seperti kasus Kristalin Eka Lestari Papua di atas.
- Set tanggal langsung via JS injection pada input date **BERBAHAYA** —
  bisa memilih tanggal yang sebenarnya TIDAK PUNYA PRODUK satelit asli
  (hasil download: nodata/hitam total), sementara preview tile browser
  tetap menampilkan citra lama yang di-cache (menyesatkan). WAJIB pakai
  klik tombol navigasi (prev/next arrow) di UI, bukan set value langsung,
  supaya hanya tanggal dengan produk asli yang terpilih.
- Preview viewport kecil di Copernicus Browser (sebelum download) TETAP
  TIDAK BISA DIPERCAYA untuk menilai cloud coverage — beberapa kali tanggal
  yang preview-nya kelihatan 100% bersih ternyata full-frame hasil
  downloadnya 30-40% berawan. Satu-satunya cara yang reliable: download
  dulu, convert True color ke PNG res penuh, baru vision_analyze.

## Kesimpulan & Rekomendasi (update 14 Nov 2026)

1. **Metodologi NDVI/NDMI tervalidasi untuk 6 dari 13 lokasi** (3 reliable
   awal + Dusun Nadi + Daya Sumber Mining + Singlurus Pratama yang baru
   diperbaiki) — bisa dipakai sebagai bukti kuantitatif kuat di presentasi
   lomba.
2. **2 lokasi (Asmin Koalindo Tuhup, Kristalin Eka Lestari Papua) masih
   caveat** meski sudah diredownload — bukan karena awan separah dulu, tapi
   karena keterbatasan baru (awan residual minor / artefak resize-mismatch).
   Bisa dipakai dengan catatan jelas di laporan, JANGAN diklaim 100% bersih.
3. Total lokasi final: 6 RELIABLE penuh, 2 CAVEAT RINGAN (Pangkalan Jambu,
   Air Liki — status awal, tidak berubah), 3 CAVEAT SEDANG (Masempo Dalle,
   Bumi Morowali Utama, Muara Hemat — status awal, tidak berubah), 2 CAVEAT
   dari hasil redownload (Asmin Koalindo Tuhup, Kristalin Eka Lestari Papua).
   **Tidak ada lagi lokasi yang UNRELIABLE sepenuhnya.**
4. **Rekomendasi teknis buat ke depan**: tambahkan band B02 (Blue) di semua
   download selanjutnya biar bisa hitung BSI standar; selalu download dulu
   baru verifikasi visual full-frame (jangan percaya viewport); jangan pakai
   JS injection untuk set tanggal (resiko nodata); kalau redownload di masa
   depan, usahakan pakai zoom level yang SAMA PERSIS dengan citra lama biar
   before/after tidak perlu di-resize paksa (hindari artefak alignment).
5. Laporan ini TIDAK menutupi kegagalan — tag TIFF valid ≠ data NDVI valid,
   preview viewport ≠ kualitas data asli, dan resize paksa bisa bikin
   artefak baru. Semua pelajaran ini sudah dicatat untuk metodologi ke depan.
