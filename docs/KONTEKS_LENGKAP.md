# KONTEKS LENGKAP — Huawei ICT Competition Innovation Track
## Illegal Mining Detector ("MineWatch" / "TambangAlert")

Terakhir diupdate: 16 November 2026
Status: Training model AI SEDANG BERJALAN di server lab lokal (GPU RTX 3060, bukan ModelArts
lagi — lihat BAGIAN 14 untuk detail & alasan). Pipeline GeoTIFF→model→cross-check izin SUDAH
terbukti jalan end-to-end (BAGIAN 14). Pipeline GeoTIFF jalan untuk 1 kasus (Neil) + 13/13
kasus (Syafa, termasuk NDVI/NDMI) — 8/13 kasus datanya reliable, 5/13 tercemar awan (BAGIAN 10)
File ini = gabungan dari PROJECT_CONTEXT.md + ground_truth_seed_list.md + momi_api_findings.md + HASIL_NDVI_NDMI.md (Syafa)

---

# BAGIAN 1 — PROMPT/BRIEF ASLI DARI NEIL (brainstorming awal bersama teman)

> ILLEGAL MINING DETECTOR — Huawei ICT Innovation Competition
>
> Project Codename: MineWatch / TambangAlert (TBD)
>
> ### RINGKASAN MASALAH
>
> Indonesia kehilangan 721.000 hektare hutan akibat tambang (2001-2023), dimana 150.000 ha adalah hutan primer. Pertambangan Tanpa Izin (PETI) tersebar dari Aceh sampai NTB, mencemari sungai dengan merkuri, menyebabkan banjir, dan merusak ekosistem.
>
> Kenapa susah ditangani:
> - Lokasi terpencil (hutan belantara, pegunungan)
> - Monitoring manual mahal & lambat
> - Luasnya jutaan hektare — manusia ga sanggup
> - Enforcement lemah — yang disegel bisa buka lagi
>
> Data pendukung:
> - 30.000 ha tambang ilegal di Kalsel saja (temuan KPK)
> - 50.000+ ha PETI emas di Jambi
> - 119 ha Taman Nasional Kerinci Seblat rusak (November 2026)
> - Kerugian negara: Rp 1 TRILIUN+ (dari lubang tak direklamasi)
> - Indonesia = sumber emisi merkuri terbesar dari tambang emas ilegal
> - Kenaikan harga emas 70% mendorong ledakan PETI (2024-2026)
>
> SDG Alignment:
> - SDG 15 — Life on Land
> - SDG 16 — Peace, Justice and Strong Institutions
> - SDG 6 — Clean Water (kontaminasi merkuri)
>
> ### SOLUSI — APA YANG KITA BANGUN
>
> Platform monitoring berbasis AI yang mendeteksi aktivitas pertambangan ilegal secara otomatis menggunakan citra satelit + data izin resmi.
>
> Core Features:
> - Automated Change Detection — AI bandingin citra satelit tiap 5 hari, detect clearing baru, lubang tambang, perubahan warna sungai
> - Legal vs Illegal Classification — Cross-check koordinat terdeteksi dengan database izin resmi (MOMI/MODI)
> - Alert System — Notifikasi otomatis ke DLHK/Polda dengan koordinat + bukti visual + severity score
> - Interactive Dashboard — Peta Indonesia, titik merah (suspect ilegal), timeline slider, before/after imagery
> - Report Generator — PDF bukti visual + koordinat buat enforcement
>
> Output Status per Titik Terdeteksi:
> - HIJAU — Ada di area IUP aktif (legal)
> - KUNING — Ada IUP tapi sudah expired
> - MERAH — Tidak ada IUP terdaftar (suspect ilegal)
>
> ### SUMBER DATA
>
> **A. Citra Satelit — Sentinel-2 (GRATIS)**
> - Sumber: Copernicus Data Space (European Space Agency)
> - URL: dataspace.copernicus.eu
> - Akses: REST API, perlu register (gratis)
> - Update: Setiap 5 hari per lokasi
> - Resolusi: 10m/pixel
> - Format: GeoTIFF (gambar + koordinat GPS)
> - Arsip: Dari Juni 2015 sampai sekarang (11 tahun data!)
> - Biaya: GRATIS, open access
>
> **B. Data Izin Tambang — MODI & MOMI (GRATIS)**
>
> MODI (Minerba One Data Indonesia) — Data Tabular
> - URL: modi.esdm.go.id
> - Isi: Nama perusahaan, jenis izin (IUP/IUPK), komoditas, status (aktif/expired/dicabut), luas area
> - API: minerba.esdm.go.id/public/iup/list (JSON, bisa filter)
> - Update: Near-real-time (sinkron dengan proses perizinan ESDM)
> - Biaya: GRATIS, publik
>
> MOMI (Minerba One Map Indonesia) — Data Spasial/Peta
> - URL: momi.minerba.esdm.go.id
> - Isi: Peta wilayah IUP/IUPK dengan koordinat polygon
> - Backend: ArcGIS Server
> - API: momi.minerba.esdm.go.id/gisportal/sharing/rest/
> - Data: 8.285 izin, 7.542 badan usaha, 8,6 JUTA hektare wilayah izin
> - Akses: GRATIS untuk "Pengguna Umum"
> - Update: Sinkron dengan MODI
>
> **C. Ground Truth / Training Data**
> - Nusantara Atlas — Peta 721.000 ha deforestasi tambang (bisa jadi training labels)
> - Berita kasus PETI — Lokasi yang sudah dikonfirmasi ilegal oleh polisi/DLHK
> - Kasus referensi: TNKS Kerinci 119 ha (Nov 2026), Kalsel 30.000 ha (KPK), Bangka Belitung timah ilegal, Jambi 50.000 ha PETI emas, PT BSJ & PT KAA nikel ilegal (ditangkap 2026)
>
> ### ARSITEKTUR TEKNIS
>
> DATA INGESTION LAYER:
> Sentinel-2 API (tiap 5 hari) -> Huawei OBS (Object Storage) -> Raw satellite imagery (GeoTIFF) + Historical archive 2015-2026
> MODI/MOMI API (sync mingguan) -> Permit polygon disimpan sebagai GeoDataFrame (geopandas), file di Huawei OBS -> Polygon IUP/IUPK + Status izin
> [KOREKSI 17 Nov 2026: bagian brainstorm ini sempat sebut GaussDB & ModelArts, TAPI keputusan final provisioning cuma 2 layanan (OBS, ECS) — GaussDB DAN ModelArts TIDAK dipakai. Cross-check jalan via `scripts/permit_crosscheck.py` pakai geopandas lokal, bukan database managed; training AI di server lab lokal, bukan ModelArts.]
>
> AI PROCESSING LAYER: ModelArts (Huawei AI Platform)
> - Model: U-Net / DeepLabV3+
> - Task: Semantic Segmentation
> - Input: 2 citra (time-1 vs time-2) di-stack sebagai multi-band
> - Output: Binary mask (changed / not changed)
> - Detects: New land clearing, New mining pits, River discoloration (merkuri), Road construction ke area hutan
>
> GEOSPATIAL CROSS-CHECK:
> - Query: ST_Contains(izin_polygon, detected_change_point)
> - Result: Inside active IUP = LEGAL / Inside expired IUP = WARNING / No IUP match = SUSPECT ILEGAL
>
> OUTPUT LAYER:
> - Astro Dashboard (Low-Code Web Platform) — Peta interaktif, timeline slider, before/after, filter, report PDF
> - SMN (Simple Message Notification) — Email alert ke DLHK/Polda
> - DataArts (Data Pipeline & Governance) — ETL, data quality, audit trail
>
> ### HUAWEI CLOUD SERVICES YANG DIPAKAI
> [KOREKSI 17 Nov 2026 (final, menggantikan koreksi 14 Nov): fix jadi **2 layanan saja: OBS (Object Storage) + ECS (Compute)**, region AP-Jakarta. ModelArts di-drop TOTAL dari scope (bukan cuma dari jalur training aktual) karena training AI sepenuhnya di server lab lokal RTX 3060 — nggak ada kebutuhan ModelArts sama sekali. Entry Form resmi (`Telkom University_kulonuwun_MineWatch_Entry Form.docx`) sudah konsisten: cuma menyebut OBS+ECS di seluruh dokumen, ModelArts tidak pernah disebut. GaussDB, SMN, Astro, DataArts, MapReduce/MRS, API Gateway tetap TIDAK dipakai.]
> ~~ModelArts, OBS, GaussDB, ECS, SMN, Astro, DataArts, MapReduce/MRS, API Gateway (9 services total)~~
>
> ### STRATEGI PRESENTASI & PROVING — Backtest Approach
> Step 1: Kumpulkan 50+ lokasi tambang ilegal yang SUDAH dikonfirmasi penegak hukum (2019-2026)
> Step 2: Ambil citra Sentinel-2 SEBELUM dan SESUDAH tambang muncul
> Step 3: Jalankan model, cross-check MOMI
> Step 4: Hitung accuracy ("47 dari 50 lokasi berhasil terdeteksi = accuracy 94%")
> Step 5: Tunjukkan early detection ("rata-rata model kami mendeteksi 3-6 bulan LEBIH AWAL dari penangkapan resmi")
>
> ### TRAINING & MODEL DETAILS
> - Model: U-Net dengan ResNet50 backbone / DeepLabV3+ alternatif
> - Input: 2 citra stack (RGB + NIR + SWIR)
> - Indices: NDVI (vegetasi), NDWI (air), BSI (tanah terbuka)
> - Training di ModelArts, GPU V100/A100, PyTorch/TensorFlow
>
> ### TIMELINE DEVELOPMENT (8 MINGGU)
> M1: Setup akun & API | M2: Download sample data | M3: Labeling (CVAT/LabelMe) | M4: Training U-Net |
> M5: Integrasi MOMI | M6: Dashboard + alert | M7: Backtest 50 lokasi | M8: Polish & presentasi
>
> ### COMPETITIVE ADVANTAGE
> Belum ada satellite AI buat illegal mining detection di Huawei ICT Competition; data semua gratis & publik; narasi Indonesia-specific kuat; bisa dibacktest dengan kasus nyata; scalable ke negara lain (Amazon, Africa).
>
> ### RISIKO & MITIGASI
> Cloud cover -> Sentinel-1 SAR backup | False positive -> manual review layer | MOMI API down -> cache polygon izin lokal/di OBS (bukan GaussDB) | Akurasi rendah -> spectral indices tambahan | Resolusi 10m kurang -> Planet/Maxar enhancement
>
> Last updated: 10 November 2026 | Status: BRAINSTORMING -> ready for development planning

---

# BAGIAN 2 — KONTEKS KOMPETISI (dari riset terpisah sebelumnya, masih relevan)

Huawei ICT Competition Innovation Track — kriteria resmi berubah per edisi, dua versi
yang terverifikasi:
- Skema 100 poin (2023-2024): Creativity 30, System/Technical complexity 25, Social value 15,
  Functional completeness 15, Presentation 15
- Skema persentase (2025-2026): Preliminary = Innovation 60% + Application Value 40%;
  Regional = Innovation 40% + Application Value 35% + Completeness&Demonstrability 15% + Presentation 10%
- Edisi yang sedang berjalan: ke-11 (2026-2027), registrasi Sept-Nov 2026, Global Final Mei 2027 Shenzhen
- Wajib pakai teknologi AI Huawei (MindSpore/CANN/ModelArts), boleh kombinasi IoT/cloud/big data
- Entri harus open-source (Gitee/GitHub) begitu lolos ke Regional/Global

---

# BAGIAN 3 — VERIFIKASI FAKTA DARI BRIEF ASLI (hasil cross-check sumber primer)

| Klaim di brief | Status | Catatan |
|---|---|---|
| 721.000 ha deforestasi tambang (150.000 ha primer), 2001-2023 | ✅ AKURAT | Nusantara Atlas/TheTreeMap (Gaveau), Juli 2024, dikonfirmasi Kompas/Jakarta Post/France24/AP |
| TNKS Kerinci 119 ha, Nov 2026 | ✅ AKURAT (presisi: 119,32 ha) | Satgas PKH, operasi 5-6 Nov 2026 |
| Kenaikan harga emas 70% (2024-2026) | ✅ AKURAT | Harga Antam Rp1.514.000 (Okt 2024) -> Rp2.574.000/gram (Okt 2026) |
| Sentinel-2 revisit 5 hari | ✅ AKURAT | Konstelasi 2 satelit di ekuator, Indonesia dapat benefit penuh |
| Kalsel 30.000 ha "temuan KPK" | ⚠️ PERLU DIPERHALUS | Angka benar (30.015 ha) tapi sumbernya analisis Stranas PK via KPK (Juni 2024), kategorinya campuran "bermasalah/ilegal/belum bayar denda", bukan 100% murni ilegal |
| Jambi "50.000+ ha PETI emas" | ❌ OUTDATED | Angka terbaru (KKI Warsi, LSM lingkungan — bukan data pemerintah) per 2025 = 60.323 ha (naik dari 52.059 ha di 2024). 75% dari luasan itu di APL, bukan kawasan hutan — jangan samakan "area teridentifikasi" dengan "hutan rusak" |
| "Indonesia = sumber emisi merkuri terbesar dari tambang emas ilegal" | ⚠️ PERLU DIPERHALUS | Yang akurat: ASGM (global, bukan cuma Indonesia) = sumber emisi merkuri terbesar DUNIA (UNEP); ASGM domestik = 69,7% dari TOTAL emisi merkuri Indonesia (IPEN 2025, 307.125 kg/tahun) |
| MOMI "Akses GRATIS untuk Pengguna Umum" | ⚠️ PERLU DIPERHALUS | Benar bisa LIHAT peta publik, TAPI REST API folder utama (IUP/IUPK aktif) butuh LOGIN — tidak ada self-registration di portal (khas ArcGIS Enterprise on-prem) |
| MODI (minerba.esdm.go.id) API | ❌ DOWN SEJAK MEI 2026+ | Konfirmasi: postingan Instagram resmi @ditjenminerba 29 Mei 2026 sudah bilang "sedang dalam perbaikan" — ini bukan gangguan sesaat, planning harus ASUMSIKAN TIDAK BISA DIPAKAI |
| "8.285 izin, 7.542 badan usaha, 8,6 juta ha" di MOMI | ❓ BELUM TERVERIFIKASI | Belum sempat dicek manual ke portal MOMI |

---

# BAGIAN 4 — EKSPLORASI API MOMI/MODI/BIG (detail teknis)

## Status Akses
- Portal MOMI: https://momi.minerba.esdm.go.id/gisportal/ — HIDUP, bisa diakses publik (beda dengan MODI yang down)
- Server REST MOMI: https://momi.minerba.esdm.go.id/gisserver/rest/services — HIDUP

## Folder yang Ditemukan di MOMI
- Daerah, EDW, FS, Hosted, KaltimPrimaCoal, Kronologis, maxxima, Pusat, Utilities -> SEMUA BUTUH TOKEN (login)
- Support -> TERBUKA TANPA LOGIN (hanya berisi data Lelang/tender, BUKAN data IUP aktif)

## Bukti Layer IUP_IUPK Ada di MOMI, Tapi Terkunci
- Query ke `Hosted/IUP_IUPK/FeatureServer` -> respon "Token Required" (BUKAN "not found")
  -> artinya layer ini MEMANG ADA di server, tinggal butuh autentikasi, bukan salah nama.
- MOMI pakai ArcGIS Enterprise Portal versi on-premise — akunnya cuma dibikinin manual oleh
  admin internal ESDM, BUKAN self-service kayak ArcGIS Online. Dicek langsung ke halaman
  sign-in: memang tidak ada opsi "Create Account"/register.

## Data yang BERHASIL diunduh tanpa login dari MOMI (di `data/momi_raw/`):
1. lelang_19_point.geojson — titik lokasi WIUP yang sedang/sudah dilelang
2. lelang_wiup_block.geojson — polygon blok wilayah WIUP lelang (nasional)
3. lelang2023_point.geojson — titik WIUP lelang 2023
   Field: nama_prov, nama_kab, pulau, lokasi, jenis_izin, nama_usaha, sk_iup, tgl_berlaku, kegiatan, dll.
   CATATAN: ini data WILAYAH YANG DILELANG (calon IUP baru), BUKAN data seluruh IUP/IUPK yang
   SUDAH AKTIF beroperasi. Belum cukup buat cross-check "ada IUP aktif atau tidak" secara lengkap.

## MODI (minerba.esdm.go.id) — DOWN
- Postingan Instagram resmi @ditjenminerba 29 Mei 2026: "sedang dalam perbaikan", arahkan ke
  layanan tatap muka RPIM. Dicek ulang beberapa kali sepanjang sesi — konsisten down sampai
  minimal 5+ bulan (per 10 Nov 2026). Audit independen GitHub (10 Okt 2026) juga menandai API
  minerba sebagai "unverified, ada pitfalls".

## geoportal.esdm.go.id
- Dicoba 3x di sesi berbeda, konsisten 503 Service Unavailable.

## SUMBER ALTERNATIF YANG BERHASIL: BIG (Badan Informasi Geospasial) - Kebijakan Satu Peta
URL: `https://kspservices.big.go.id/satupeta/rest/services/PUBLIK/PERIZINAN_DAN_PERTANAHAN/MapServer/4`
Status: PUBLIK PENUH, TANPA LOGIN, berhasil diunduh semua (pagination 5x1000 record + sisa).

Hasil: **4.608 polygon IUP/IUPK/PKP2B/IPR/KK/SIPB se-Indonesia**, field lengkap:
nama operator (nmoprt), nomor SK (skblok), tanggal mulai/berakhir (datstr/datend),
luas blok hektare (lublok), status, komoditas (commdt), lokasi, provinsi, kabupaten.

Disimpan di: `data/momi_processed/iup_izin_tambang_big_satupeta_merged.geojson` (4.608 fitur, semua unik)

### CATATAN PENTING — Data BIG ini SUDAH LAWAS:
- Tanggal data dimasukkan ke sistem (datcrte): rentang 2019-05-14 s/d 2022-06-28
  -> snapshot terakhir sekitar PERTENGAHAN 2022, BUKAN near-real-time
- 67,3% (3.102 dari 4.607) izin sudah lewat tanggal berakhirnya (datend) per hari ini
- Izin baru yang terbit 2023-2026 (termasuk kasus TNKS Kerinci Nov 2026, Jambi, dst) TIDAK ADA di dataset ini
- Cakupan Papua sangat tipis: cuma 14 entri untuk SELURUH wilayah Papua (vs 4.608 se-Indonesia).
  "Papua Tengah" belum dikenali sebagai provinsi terpisah di snapshot ini (baru dimekarkan 2022/2023)
- Dicek juga: tidak ada metadata "editingInfo"/last-edit yang menunjukkan versi lebih baru tersedia
  di portal yang sama

### Kesimpulan soal BIG
Dataset BIG ini BAGUS sebagai titik awal/baseline + backup kalau MOMI/MODI bermasalah,
TAPI TIDAK CUKUP SENDIRIAN untuk cross-check status izin TERKINI (2023-2026). Opsi lanjutan:
(a) akses MOMI/MODI yang update (perlu akun internal/kontak resmi ESDM), atau
(b) cari update terbaru data KSP BIG (belum ketemu versi lebih baru di portal/layer lain), atau
(c) terima keterbatasan ini dan JELASKAN ke juri: baseline izin pakai data 2022 + verifikasi
    manual kasus-kasus terbaru (2023-2026) pakai berita/laporan resmi yang sudah dikonfirmasi.

## Bukti Awal Konsep (proof of concept kasar, level agregat bukan polygon-presisi)
Cross-check Jambi: izin EMAS LEGAL se-Jambi cuma 3 (milik Antam Tbk), total 21.879 ha,
vs area PETI emas teridentifikasi 60.323 ha (KKI Warsi 2025) -> **izin legal cuma nutupin ~36%**.
Kabupaten Kerinci cuma punya 1 izin resmi (SIRTU 5,6 ha, bukan emas) di seluruh database.

---

# BAGIAN 5 — GROUND TRUTH SEED LIST: 13 KASUS TAMBANG ILEGAL TERKONFIRMASI

Status presisi koordinat WAJIB dibaca sebelum dipakai — titik di bawah ini sebagian
besar adalah **centroid desa/kecamatan/kabupaten atau centroid polygon izin resmi**,
BUKAN koordinat GPS persis titik lubang tambang (kecuali disebut lain). Dipakai sebagai
starting point nyari area citra satelit; lokasi tambang persisnya tetap perlu dicek
manual di citra (before/after).

## JAMBI — Taman Nasional Kerinci Seblat (operasi Satgas PKH, 5-6 Nov 2026)

### 1. Penetai, Desa Muara Hemat, Kec. Batang Merangin, Kab. Kerinci
- Luas: 119,32 ha | Komoditas: Emas | Status: DIKONFIRMASI, operasi penertiban selesai
- Koordinat (centroid desa, Wikipedia): **-2.19694, 101.76250**
- Koordinat alternatif (confluence sungai, OSM/WaterwayMap): -2.1972, 101.7606 (konsisten)
- Catatan lokasi lebih presisi: lokasi sebenarnya di sepanjang "Sungai Penetai" dan
  pertemuan "Sungai Sijau" dengan "Sungai Penetai" — tim menyisir ~9 km hulu-hilir
  (16-19 Okt 2026). Sungai Penetai sendiri tidak ketemu di OSM (anak sungai kecil).
- Sumber: mediaindonesia.com, kompas.com, detik.com, cnnindonesia.com (6-9/11/2026), id.wikipedia.org, waterwaymap.org

### 2. Desa Air Liki, Kec. Tabir Barat, Kab. Merangin
- Komoditas: Emas | Status: DIKONFIRMASI (tambang + alat berat ditemukan sepanjang sungai, dari foto drone + laporan warga)
- Koordinat (centroid desa, OSM): **-1.9516528, 101.7675103**
- Sumber: jambi.tribunnews.com (7/11/2026)

### 3. Desa Baru Pangkalan Jambu, Kec. Pangkalan Jambu, Kab. Merangin
- Komoditas: Emas | Status: DIKONFIRMASI (1 dari 3 titik operasi awal)
- Koordinat (centroid KECAMATAN — lebih kasar dari desa): **-2.1243875, 101.8707032**
- Sumber: viva.co.id, jambi.tribunnews.com

## PAPUA TENGAH — Nabire

### 4. PT Kristalin Eka Lestari (KEL) — Kali Musairo, Distrik Makimi, Kab. Nabire ⭐ KASUS TERBAIK
- Status: IUP DICABUT resmi (SK Menteri Investasi/BKPM No.20261012-01-0001, 22 Okt 2026)
- Luas ilegal: 275,9025 ha total = **170,4459 ha DI DALAM WIUP** (tanpa PPKH) + **105,4566 ha DI LUAR WIUP**
- WIUP resmi (dicabut): 3.500 ha | Komoditas: Emas | Produksi diperkirakan 300-500 kg/bulan
- Koordinat (centroid lokalitas Makimi, OSM): **-3.1389082, 135.8248429**
- Sumber: kompas.com, story.kejaksaan.go.id (resmi Kejagung), BBC Indonesia, suara.com, big.go.id
- **Tidak ketemu di dataset BIG** — dataset BIG cuma punya 14 entri untuk seluruh Papua
  (cakupan sangat tipis + Papua Tengah baru jadi provinsi terpisah 2022/2023). Ini keterbatasan
  cakupan data, bukan salah nama pencarian.

## SULAWESI TENGGARA — Konawe Utara (kasus korupsi nikel 2013-2025, masih berjalan Nov 2026)

### 5. PT BSJ & PT KAA — Konawe Utara ✅ SUDAH KETEMU NAMA RESMI + POLYGON
- Status: TERSANGKA KORPORASI (Kejagung, 9 Nov 2026) — IUP kedaluwarsa, diperpanjang 3x
  via status "suspend" secara tidak sah. Komoditas: Nikel.
- **PT BSJ = PT Bumi Sentosa Jaya** (CNN Indonesia, 10/11/2026, luas IUP berita: 1.030 ha)
  -> ketemu di dataset BIG, luas **1.030 ha** (PERSIS SAMA) -> centroid **-3.425668, 122.368728**
- **PT KAA = PT Karya Alam Abadi** (inisial "KAA" cocok sempurna, luas IUP berita: 1.036 ha)
  -> ketemu di dataset BIG, luas **1.036 ha** (PERSIS SAMA) -> centroid **-3.391587, 122.341102**
- BONUS: **PT ANI = PT Apollo Nickel Indonesia** (luas IUP berita: 106 ha) -> ketemu, luas
  **106 ha** (PERSIS SAMA), centroid belum dihitung
- Confidence: TINGGI — match ganda (inisial nama + luas hektare persis sama angka berita resmi)
- ANOMALI yang perlu dicatat: field `datend` di dataset BIG untuk BSJ & KAA menunjukkan tahun
  ~2037, padahal berita bilang izin berakhir 2014/2015/2018 (ANTAR SUMBER BERITA SENDIRI TIDAK
  KONSISTEN soal tahun persisnya). Jangan pilih salah satu angka dan klaim final — perlu
  verifikasi lebih lanjut sebelum dipakai sebagai "bukti tanggal expired".
- Jaringan 7 perusahaan terafiliasi (menurut berita): PT BSJ, KAA, ANI, AMI, AMID, DAA, HJ
  (uang Rp11,7 miliar disita, diduga milik Arif Kurniawan/AK)
- Sumber: tirto.id, metrotvnews.com, kompas.id, beritasatu.com, antaranews.com, cnnindonesia.com,
  koranmanado.co.id (semua 9-10/11/2026)

### 6. PT Kembar Emas Sultra (PT KES) — Konawe Utara
- Status: DISEGEL sebagian oleh Satgas PKH — area 26,06 ha (dari total 2 IUP legal 467+103=570 ha)
  beroperasi TANPA PPKH di kawasan hutan. Komoditas: Nikel.
- Polygon 103 ha ketemu di dataset BIG (PERSIS cocok sama "IUP no.255/2011, 103 ha" di berita)
  -> centroid **-3.293246, 122.292514**
- Sumber: muarasultra.com (cek silang via MODI oleh jurnalis)

### 7. PT Masempo Dalle — Desa Morombo Pantai, Konawe Utara
- Status: 2 TERSANGKA (Bareskrim Polri, LP 4 Des 2025) — pengerukan tanah+nikel DI LUAR IUP
  yang berlaku, gagal tunjukkan IUP sah untuk area tsb. Komoditas: Nikel.
- Koordinat geocoding desa Morombo (terdekat yg ketemu): **-3.3472840, 122.2233351**
- Ketemu 2 polygon IUP resmi perusahaan ini di dataset BIG: 103,2 ha (centroid -3.384901,
  122.259844) dan 201,3 ha (centroid -3.359706, 122.251510) — TAPI pelanggarannya kemungkinan
  BUKAN di salah satu polygon ini (berita bilang "gagal tunjukkan IUP UNTUK AREA OPERASIONAL
  tsb"), jadi 2 centroid ini cuma referensi "perusahaan beroperasi di area mana", bukan titik
  pelanggaran. Jaraknya ~5-10km dari geocoding desa Morombo — konsisten 1 wilayah operasi.
- Sumber: news.detik.com (16/3/2026)

## SULAWESI TENGAH — Morowali (operasi Satgas PKH, 4-5 Nov 2025)

### 8. Desa Laroenai, Kec. Bungku Pesisir, Kab. Morowali
- Luas: 62,5 ha | Komoditas: Nikel | Status: DITERTIBKAN Satgas PKH (ditinjau Menhan+Panglima TNI+Kapolri)
- Koordinat (centroid desa): **-3.0501986, 122.2776217**
- Sumber: kompas.tv, adatah.com, kemhan.go.id (4-5/11/2025)

### 9. PT Bumi Morowali Utara (BMU) + PT Daya Sumber Mining Indonesia (DSMI) — Morowali
- Luas bukaan tanpa IPPKH/PPKH: 62,15 ha = **46,03 ha DI DALAM wilayah IUP** + **15,94 ha DI LUAR wilayah IUP**
  (angka total perusahaan 66,0144 ha termasuk sebagian yang sudah berizin)
- Komoditas: Nikel | Potensi denda: Rp2,35 triliun
- Dataset BIG ketemu "BUMI MOROWALI UTAMA" (polygon 1.963 ha -> centroid -3.064594, 122.248983)
  — CATATAN: nama di dataset "UTAMA" vs berita "UTARA", kemungkinan typo di salah satu sumber
  atau 2 perusahaan beda — JANGAN klaim 100% sama tanpa verifikasi tambahan.
- PT Daya Sumber Mining Indonesia ketemu persis: polygon 2.199 ha -> centroid **-2.756180, 121.827973**
- Sumber: nikel.co.id (5/11/2025) — 1 dari 16 perusahaan diidentifikasi, 9 sudah terverifikasi

## KALIMANTAN TENGAH — Murung Raya

### 10. PT Asmin Koalindo Tuhup (AKT) — Murung Raya
- Luas: 1.699 ha | Komoditas: Batubara | Status: DIKUASAI NEGARA (22/1/2026)
- IUP dicabut sejak 2017 (PKP2B dijadikan jaminan utang tanpa izin pemerintah)
- Denda: Rp4,2 triliun (Rp354 juta/hektare, SK Menteri ESDM No.391K/KMB/01.Men/2025)
- TIDAK ketemu persis di dataset BIG (wajar, izin sudah dicabut sejak 2017). Tapi ketemu 4
  konsesi batubara "sekelompok" (nama mengandung "Asmin"/"Tuhup") di Murung Raya-Kapuas:
  - ASMIN BARA JAAN: -0.784849, 114.496212 (7.298 ha)
  - ASMIN BARA BRONANG: -0.912333, 114.414167 (24.980 ha)
  - TUHUP COAL MINING: -0.653800, 114.807424 (11.260 ha)
  - LAUNG TUHUP COAL: -0.143889, 114.665778 (12.820 ha)
  REKOMENDASI: pakai area yang dilingkupi 4 titik ini (kira-kira -0.14 s/d -0.91 lat,
  114.41 s/d 114.81 lon) sebagai ZONA PENCARIAN citra satelit, bukan 1 titik presisi —
  jauh lebih baik dari centroid kabupaten Murung Raya (-0.068, 114.173, di luar klaster ini).
- Sumber: bpkp.go.id (resmi, 23/1/2026)

## KALIMANTAN TIMUR — Kutai Kartanegara

### 11. PT Singlurus Pratama — Tahura Bukit Soeharto, Samboja, Kutai Kartanegara
- Luas: 111,71 ha | Komoditas: Batubara | Status: DIKUASAI NEGARA (31/8/2026)
- Polygon 21.699 ha ketemu di dataset BIG -> centroid **-1.030749, 117.002146**
  (konsesi besar, bagian ilegal 111,71 ha cuma sepotong kecil dari luas polygon ini)
- Sumber: kalsel.antaranews.com (31/8/2026)

## KEPULAUAN BANGKA BELITUNG

### 12. DAS Kampak, Kec. Jebus, Kab. Bangka Barat
- Komoditas: Timah | Status: DITERTIBKAN BERULANG KALI (Agustus-November 2026, masih berulang)
- Catatan: kasus berulang (ditertibkan tapi sempat diduga beroperasi lagi) — bagus buat
  contoh "butuh monitoring berkelanjutan", bukan cuma 1x deteksi
- Koordinat (centroid desa Jebus): **-1.7711586, 105.4650541**
- Sumber: babel.antaranews.com, wowbabel.com, bangka.tribunnews.com (Okt-Nov 2026)

### 13. Dusun Nadi, Kec. Lubuk Besar, Kab. Bangka Tengah
- Komoditas: Timah | Status: DISIDAK Jaksa Agung langsung (19/11/2025)
- Potensi kerugian negara: Rp12,9 triliun | Puluhan ekskavator disita
- Koordinat (centroid desa Lubuk Besar, dusun spesifik belum ketemu): **-2.6298323, 106.5962804**
- Sumber: bangka.tribunnews.com (19/11/2025)

## Ringkasan tingkat presisi (per 10 Nov 2026)
- **Tier 0/1 (polygon izin ASLI, paling akurat)**: PT Bumi Sentosa Jaya, PT Karya Alam Abadi,
  PT Apollo Nickel Indonesia, PT Singlurus Pratama, PT Kembar Emas Sultra, PT Masempo Dalle
  (2 polygon), PT Daya Sumber Mining Indonesia, (PT Bumi Morowali Utama — perlu verifikasi nama)
- **Tier 2 (geocoding desa, OSM/Wikipedia, radius ~1-5km)**: Muara Hemat, Air Liki, Laroenai,
  Morombo, Jebus, Lubuk Besar, Makimi
- **Tier 3 (klaster area, bukan titik presisi)**: PT Asmin Koalindo Tuhup (4 konsesi tetangga)
- **Tier 4 (kecamatan/kabupaten, kasar)**: Desa Baru Pangkalan Jambu
- Hanya **1 dari 13 kasus** yang masih belum ada titik sama sekali selain geocoding desa:
  PT Kristalin Eka Lestari (keterbatasan cakupan data Papua di BIG, bukan salah nama)

## Metodologi pencarian & keterbatasan jujur
Semua koordinat dicari via OpenStreetMap Nominatim (geocoding gratis & terbuka) berdasarkan
nama desa/kecamatan/kabupaten yang disebut di berita resmi (Kejagung, Kemhan, BPKP, Satgas PKH)
atau media arus utama terverifikasi (Kompas, Antara, BBC, Detik, dll), DAN/ATAU dari centroid
polygon izin resmi perusahaan (cross-check nama ke dataset BIG KSP). TIDAK ADA koordinat yang
dikarang/ditebak. Beberapa nama tempat (Sungai Penetai, Dusun Nadi, Morombo Pantai) tidak ketemu
persis di OSM, jadi dipakai level terdekat yang tersedia — ini DISEBUTKAN eksplisit di tiap
entri, bukan disamarkan seolah-olah presisi.

---

# BAGIAN 6 — STRUKTUR FOLDER PROYEK

```
/home/ubuntu/huawei-ict-illegal-mining/
├── data/
│   ├── big_satupeta_iup/          # 5 file mentah hasil pagination download BIG KSP
│   ├── momi_processed/            # gabungan bersih (4.608 polygon IUP, siap pakai)
│   └── momi_raw/                  # data lelang WIUP dari MOMI (bukan IUP aktif)
└── docs/
    ├── KONTEKS_LENGKAP.md         # file ini (gabungan semua)
    ├── PROJECT_CONTEXT.md         # versi sebelum digabung (masih ada, redundant)
    ├── momi_api_findings.md       # versi sebelum digabung (masih ada, redundant)
    └── ground_truth_seed_list.md  # versi sebelum digabung (masih ada, redundant)
```
Catatan: folder ini terpisah total dari proyek lain (OpenRAN-Dashboard/benchmark-5g) di
`/home/ubuntu/` — tidak ada file yang tercampur.

---

# BAGIAN 7 — CHECKLIST STATUS PROYEK

## Sudah dikerjakan
- [x] Verifikasi semua klaim data kunci di brief asli ke sumber primer
- [x] Eksplorasi & dokumentasi status API MOMI/MODI (termasuk kenapa down/gated)
- [x] Temukan & download sumber alternatif (BIG KSP) — 4.608 polygon IUP
- [x] Proof of concept kasar (level agregat) yang mendukung tesis proyek
- [x] Kumpulkan 13 kasus ground truth dari sumber resmi/media terverifikasi
- [x] Geocode semua kasus (OSM/Wikipedia) + cross-check ke polygon izin asli
- [x] Temukan nama resmi PT BSJ, PT KAA, PT ANI + polygon izinnya (match ganda nama+luas)

## Belum dikerjakan / langkah selanjutnya
- [x] Download citra Sentinel-2 ASLI (GeoTIFF) untuk 13/13 kasus — **dikerjakan Syafa**, lihat BAGIAN 10
- [x] Hitung NDVI/NDMI kuantitatif untuk 13 kasus — **dikerjakan Syafa**, lihat BAGIAN 10
- [ ] Download ulang 5 lokasi yang tercemar awan tebal (lihat BAGIAN 10) dengan tanggal yang benar-benar bersih
- [ ] Download band B02 (Blue) untuk semua lokasi agar bisa hitung BSI standar (saat ini pakai NDMI sebagai proxy)
- [ ] Tambah kasus dari provinsi lain (Sumatera luar Jambi, Kalimantan Barat/Selatan per-lokasi)
- [ ] Manual annotation/labeling (CVAT/LabelMe) untuk training data U-Net
- [ ] Setup Huawei Cloud account (OBS, ECS — 2 layanan final, BUKAN ModelArts/GaussDB) — nunggu approval akses (Syafa)
- [ ] Opsional: coba request akses resmi MOMI/MODI via jalur ESDM untuk data IUP terkini
  (snapshot BIG yang ada baru sampai ~2022, perlu data 2023-2026 untuk kasus-kasus terbaru)
- [ ] Opsional: verifikasi lebih lanjut nama "PT Bumi Morowali Utama" vs "Utara" (kemungkinan beda entitas)
- [ ] Coba citra Sentinel-1 SAR (radar, tembus awan) buat lokasi yang selalu ketutup awan (Papua)

---

# BAGIAN 8 — PILOT TEST VISUAL SENTINEL-2 (10 Nov 2026, lanjutan sesi sama)

## Tujuan
Sebelum invest waktu ke setup berat (Huawei Cloud, training model AI), cek dulu secara VISUAL
MANUAL: apakah perubahan akibat tambang ilegal ini BENERAN keliatan di citra Sentinel-2 10m/pixel?
Kalau nggak keliatan jelas, arsitektur AI-nya perlu dirombak dari awal.

## Setup Akun Copernicus
- Neil daftar akun sendiri di dataspace.copernicus.eu (kredensial disimpan di vault Hermes,
  bukan di plain text manapun — lihat skill `browser-login-credentials`)
- Login berhasil lewat browser otomatis pakai `browser_vault` (fill password dari vault,
  tanpa pernah melihat password-nya secara langsung)
- Dicek tab "Applications": client OAuth resminya `cdse-public` (status "In use") — ini client
  standar buat API access (OAuth2 password-grant), TAPI karena password disimpan di vault (nggak
  pernah terlihat), token API lewat curl/terminal TIDAK BISA dibuat langsung. Solusinya: pakai
  SESI BROWSER yang udah login buat akses Copernicus Browser (UI peta), bukan OAuth token mentah.

## Metodologi
Pakai Copernicus Browser (browser.dataspace.copernicus.eu) — jalan di browser, bukan command line.
Teknik: klik "Show latest date" buat snap ke tanggal yang beneran ada citranya (JANGAN ketik
tanggal sembarang — bisa nyasar ke basemap kosong kalau nggak ada pass Sentinel di tanggal itu),
lalu klik panah "<" berkali-kali buat mundur ke tanggal lama (termasuk lompat jauh ke 2018-2020
buat baseline "before"). Collapse sidebar kiri sebelum screenshot biar framing penuh & konsisten.
Detail lengkap metodologi ini udah disimpan sebagai skill `satellite-imagery-change-analysis`.

## Hasil per Kasus

### 1. TNKS Kerinci (emas, Jambi) — Desa Muara Hemat (-2.19694, 101.76250)
- Perbandingan: 2018-09-28 ("before") vs 2026-08-22 ("after")
- Hasil: Sinyal ADA tapi HALUS — bercak coklat-oranye tidak beraturan ngikutin lekukan sungai
  di citra 2026, nggak ada di citra 2018. Pola ini KONSISTEN sama ciri PETI emas skala kecil
  (bercak tersebar nempel di sungai, bukan satu area bersih besar)
- CATATAN JUJUR: pola kecil kayak gini gampang disalahartikan sebagai sedimen sungai alami atau
  artefak haze — ini "plausible/konsisten", BUKAN "confirmed" tanpa validasi lebih lanjut
  (misal citra resolusi lebih tinggi atau overlay GPS lapangan)

### 2. PT Kristalin Eka Lestari (emas, Nabire, Papua Tengah) — Makimi (-3.1389082, 135.8248429)
- Hasil: INCONCLUSIVE — tertutup awan tebal di hampir semua tanggal yang dicoba (termasuk
  tanggal "latest" Okt 2026). Ini KETERBATASAN DATA, bukan "tidak ada tambang" — Papua secara
  umum terkenal sulit dapat citra optik bersih karena curah hujan tinggi
  REKOMENDASI: coba Sentinel-1 SAR (radar, bisa tembus awan) buat lokasi ini spesifik

### 3. PT BSJ/PT KAA — Bumi Sentosa Jaya & Karya Alam Abadi (nikel, Konawe Utara, Sultra)
  (-3.425668, 122.368728)
- Perbandingan: 2020-08-29 ("before") vs 2026-11-06 ("after")
- Hasil: Sinyal SANGAT JELAS — di 2020 area tambang masih relatif kecil & terkonsentrasi,
  di 2026 area tambang MELUAS DRASTIS, menutupi hampir seluruh semenanjung, lengkap dengan
  jaringan jalan akses yang motong-motong kanopi hutan, DAN air laut di pesisir berubah
  kecoklatan (indikasi sedimen runoff dari aktivitas tambang)
- Ini kasus PALING MUDAH dibuktikan secara visual dari 3 kasus yang dicoba

## Kesimpulan Pilot Test
1. **Pendekatan "AI deteksi perubahan dari citra Sentinel-2" LAYAK DITERUSKAN** — 2 dari 3 kasus
   kasih sinyal visual yang jelas (1 di antaranya sangat kuat), bukan harus dirombak total.
2. **Komoditas tambang industrial (nikel/batubara) kemungkinan JAUH lebih gampang dideteksi
   dibanding tambang emas rakyat/PETI** — skala operasinya ratusan-ribuan hektare pakai alat
   berat (kontras tinggi vs hutan), sementara PETI emas skalanya kecil & tersebar (gampang
   disalahartikan sebagai sedimen sungai alami di resolusi 10m/pixel)
3. **Cloud cover di hutan hujan tropis (terutama Papua) adalah hambatan nyata** — ini bukan
   temuan baru, udah diantisipasi di brief asli (mitigasi: Sentinel-1 SAR), tapi pilot test ini
   mengonfirmasi hambatan itu BENERAN terjadi di praktik, bukan cuma risiko teoretis
4. **Implikasi strategi presentasi ke juri**: pertimbangkan nge-highlight kasus nikel/batubara
   (Sulawesi/Kalimantan) sebagai showcase utama karena paling mudah dibuktikan & dampaknya
   visual jelas, sementara kasus emas Jambi tetap dimasukkan tapi dengan framing yang realistis
   ("butuh model yang lebih sensitif buat skala kecil") — supaya klaim ke juri nggak overclaim

## Batasan Metodologi (penting, jangan disamarkan)
- Ini PERBANDINGAN VISUAL MANUAL oleh manusia (gw), BUKAN deteksi otomatis/kuantitatif oleh model
- Baru 3 dari 13 kasus yang dicoba — belum cukup buat klaim "model AI terbukti akurat" ke juri
- Screenshot yang diambil BUKAN citra GeoTIFF asli (resolusi penuh + band spektral lengkap) —
  itu masih harus didownload terpisah buat proses training/testing model beneran
- Temuan ini adalah GO/NO-GO CHECK atas hipotesis dasar proyek ("sinyalnya ada atau nggak di
  resolusi ini"), BUKAN pengganti validasi kuantitatif nanti

---

# BAGIAN 9 — DOWNLOAD CITRA GEOTIFF ASLI + ANALISIS KUANTITATIF PERTAMA (10 Nov 2026)

## Cara Download yang Berhasil (tanpa OAuth token mentah)
Karena password Copernicus disimpan di vault (nggak pernah terlihat langsung oleh asisten),
OAuth token lewat curl/terminal TIDAK BISA dibuat. Solusi yang jalan: pakai sesi BROWSER yang
udah login, buka Copernicus Browser, klik icon "Image download" (gambar+panah di sidebar kanan),
pilih tab **"Analytical"** (bukan "Basic" — Basic cuma kasih gambar visual tanpa georeferensi),
set:
- Image format: **TIFF (16-bit)** (ada juga pilihan TIFF 8-bit dan 32-bit float)
- Image resolution: **HIGH** (631x835 px buat area ini)
- Layer: **True color** (RGB biasa; bisa juga pilih Raw bands B01-B12 buat spectral index nanti)

File hasil download otomatis masuk ke `~/Downloads/` dengan nama format
`<tanggal>_Sentinel-2_L2A_True_color.tiff` — lalu dipindah manual ke folder proyek.

CATATAN: sesi login Copernicus Browser gampang expire/reset kalau ada full-navigation (goto_url)
baru — harus login ulang tiap kali itu terjadi (bukan bug, emang perilaku SPA-nya). Login ulang
pakai metode yang sama kayak awal (fill_input #username + browser_vault fill + klik #kc-login).

## File yang Berhasil Didownload
Lokasi: PT Bumi Sentosa Jaya & PT Karya Alam Abadi, Konawe Utara, Sulawesi Tenggara
(-3.425668, 122.368728) — disimpan di `data/sentinel2_pilot/konawe_utara_bsj_kaa/`:
- `before_2021-03-22.tiff` (3,05 MB) — GeoTIFF asli, True color, resolusi HIGH
- `after_2026-11-06.tiff` (3,06 MB) — GeoTIFF asli, True color, resolusi HIGH

Validasi: dibuka pakai Pillow (Python), dikonfirmasi punya GeoTIFF tags asli (tiepoint koordinat,
GeoKeyDirectory, datum "WGS 84") — BUKAN screenshot biasa, bisa langsung dibuka di QGIS/rasterio
dengan koordinat yang benar.

## Analisis Kuantitatif Pertama (heuristik kasar, BUKAN NDVI/BSI resmi)
Pakai Python (numpy+Pillow) hitung fraksi piksel "kecoklatan/terbuka" (R>G & R>80, proxy kasar
buat tanah terbuka vs vegetasi) di kedua citra:
- Before (2021-03-22): 8,5% piksel kecoklatan/terbuka
- After (2026-11-06): 13,8% piksel kecoklatan/terbuka
- **Perubahan: +5,3 poin persentase**, setara perkiraan **~277 ha** area baru yang jadi
  terbuka/terganggu (dari cakupan citra ~52 km²)

CATATAN JUJUR WAJIB DIPATUHI: ini heuristik RGB sederhana (R>G), BUKAN NDVI (perlu band NIR/B08)
atau BSI (perlu band SWIR/B11) yang sebenarnya direncanakan di arsitektur. Angka 277 ha ini
PERKIRAAN KASAR UNTUK ILUSTRASI, belum tervalidasi, dan BELUM BOLEH diklaim sebagai hasil model
ke juri tanpa dihitung ulang pakai spectral index yang bener (butuh download band B04/B08/B11
tambahan, bukan cuma True color RGB).

## Status Update
Pipeline "download citra asli" SEKARANG TERBUKTI JALAN end-to-end: login vault -> Copernicus
Browser -> Analytical download -> GeoTIFF tervalidasi -> analisis Python. Siap discale ke kasus
lain (12 kasus tersisa) dan ke band spektral lengkap (NIR/SWIR) buat NDVI/BSI yang bener.

---

# BAGIAN 10 — KERJAAN SYAFA: DOWNLOAD 13 LOKASI + NDVI/NDMI (14 Nov 2026)

Dikerjakan oleh **Siti Nurhayati Syafaningrum ("Syafa")**, anggota tim kulonuwun, lewat sesi
Hermes terpisah (chat Telegram sendiri, judul sesi "Hwawei") — tapi di environment/filesystem
Linux yang **sama persis** dengan punya Neil, jadi semua file di bawah ini otomatis masuk ke
folder proyek yang sama tanpa perlu transfer manual. Tidak ada konflik dengan kerjaan Neil
(folder/kasus yang disentuh beda; kasus `konawe_utara_bsj_kaa` milik Neil otomatis di-skip oleh
script Syafa karena band-nya tidak lengkap untuk NDVI).

## 10.1 — Download GeoTIFF 13 Lokasi Ground Truth

Syafa mendownload citra Sentinel-2 before/after untuk **13/13 kasus ground truth** (BAGIAN 5),
masing-masing 4 band per tanggal: **True color, B04 (merah), B08 (NIR), B11 (SWIR)** — total
**104 file GeoTIFF baru**, semua lolos verifikasi metadata (geotag valid, bukan file nodata
kosong). Disimpan di `data/sentinel2_pilot/<nama_kasus>/{before,after}_<tanggal>/`. Ringkasan
tanggal & koordinat per kasus ada di `data/sentinel2_pilot/download_progress_log.md`.

## 10.2 — Perhitungan NDVI/NDMI

Script: `scripts/compute_ndvi_ndmi.py` (Python 3.10, numpy+PIL+matplotlib). Metodologi:
- **NDVI** = (B08 − B04) / (B08 + B04) — indeks vegetasi standar.
- **NDMI** = (B08 − B11) / (B08 + B11) — dipakai sebagai proxy bare-soil pengganti BSI standar,
  karena band B02 (Blue) belum didownload (trade-off yang didokumentasikan, bukan disembunyikan).
- Metrik utama: **"sharp NDVI loss pixel fraction"** (% piksel yang NDVI-nya turun >0.2 dari
  before ke after) — lebih andal daripada rata-rata NDVI satu frame, karena area tambang
  biasanya cuma sebagian kecil dari frame 1491×835 px.

## 10.3 — TEMUAN PENTING (self-caught oleh Syafa, dilaporkan jujur)

Verifikasi otomatis sebelumnya ("tag GeoTIFF valid + pixel bukan nodata murni") **TIDAK CUKUP**
untuk menjamin kualitas data — tidak menangkap **kontaminasi awan** (piksel awan reflektansinya
tinggi, bukan nol, jadi lolos cek otomatis tapi tetap merusak NDVI). Setelah Syafa cross-check
visual manual (vision_analyze) ke semua 13 pasang before/after:

| Status | Jumlah | Lokasi |
|---|---|---|
| ✅ Reliable | 3 | Kembar Emas Sultra, DAS Kampak (Bangka Barat), Laroenai (Morowali) |
| ⚠️ Caveat ringan | 2 | Pangkalan Jambu, Air Liki (Jambi) |
| ⚠️⚠️ Caveat sedang | 3 | Masempo Dalle (Konawe Utara), Bumi Morowali Utama, Muara Hemat (Jambi) |
| ❌ Unreliable (awan tebal) | 5 | Asmin Koalindo Tuhup (Murung Raya), Dusun Nadi (Bangka Tengah), Daya Sumber Mining, Singlurus Pratama, Kristalin Eka Lestari (Papua) |

Detail angka NDVI delta + alasan per kasus: `analysis/ndvi_ndmi/HASIL_NDVI_NDMI.md` dan
`analysis/ndvi_ndmi/ndvi_ndmi_results.json`. Visualisasi before/after/delta-heatmap per kasus:
`analysis/ndvi_ndmi/*.png`.

Contoh kasus unreliable paling ekstrem: **Asmin Koalindo Tuhup** NDVI delta tercatat naik
+0.529 (seolah vegetasi PULIH drastis) — ini **artefak awan**, bukan regrowth beneran, karena
citra "before" (2019-06-30) tertutup awan tebal >50% frame.

## 10.4 — Rekomendasi Syafa untuk Lanjutan

1. **Kembar Emas Sultra siap dipakai sebagai contoh bukti kuantitatif di presentasi lomba**
   (validasi visual paling kuat — area merah NDVI delta persis bertumpuk dengan area tambang
   terbuka yang terlihat di citra after).
2. 5 lokasi unreliable perlu **didownload ulang** dengan tanggal yang benar-benar bersih di
   seluruh frame (bukan cuma viewport kecil yang terlihat saat screenshot browser — file yang
   didownload mencakup area lebih luas yang bisa beda cuaca dari yang terlihat di layar).
3. Tambahkan **band B02 (Blue)** di semua download selanjutnya untuk bisa hitung BSI standar,
   dan pakai indikator cloud-percentage di Copernicus Browser (bukan cuma visual sekilas).

## 10.5 — Sisa Jobdesk Syafa yang Belum Disentuh

- Setup Huawei Cloud (ModelArts, OBS, dll) — menunggu approval akses
- Data Sentinel-1 SAR (radar, tembus awan — relevan untuk lokasi Papua yang selalu berawan)
- Request akses resmi MOMI/MODI via jalur ESDM
- Manual labeling via CVAT untuk training data

## 10.6 — Catatan Koordinasi (penting)

Neil dan Syafa memakai **host/filesystem Linux yang sama** lewat sesi Hermes terpisah masing-
masing — artinya ada risiko tabrakan kalau keduanya mengedit file yang sama secara bersamaan.
Sejauh ini (per 14 Nov 2026) tidak ada konflik karena folder/kasus yang disentuh berbeda, tapi
sebaiknya dikoordinasikan siapa pegang task/folder mana ke depannya.

---

# BAGIAN 11 — MOMI "PENGGUNA UMUM": DEAD END, BUKAN PENDAFTARAN (14 Nov 2026)

Task "request akses MOMI/MODI via Pengguna Umum" (diusulkan Syafa) dicek Neil — ternyata **salah
premis**. Dari User Guide resmi MOMI:

> "User tidak dapat membuat credential secara mandiri untuk mengakses MOMI. Seluruh akses user
> membutuhkan credential **kecuali** tautan PENGGUNA UMUM."

Artinya:
- **"Pengguna Umum" BUKAN akun yang perlu didaftarin** — itu link publik TANPA LOGIN sama sekali
  (dicek langsung: `momi.minerba.esdm.go.id/public/` -> redirect ke
  `geoportal.esdm.go.id/minerba` -> **"SISTEM SEDANG DALAM PERBAIKAN"**, konsisten dengan status
  down MODI yang udah dicatat sebelumnya).
- Buat akun beneran (yang berpotensi unlock layer IUP_IUPK yang terkunci), **tidak ada jalur
  pendaftaran mandiri** — credential cuma dikasih langsung oleh admin MOMI, kemungkinan terbatas
  untuk instansi/lembaga resmi.
- Halaman Sign In di portal (ArcGIS Enterprise) juga tidak punya tombol "Create Account".

**Kesimpulan: task ini dihentikan, bukan dilanjutkan** — tidak ada proses pendaftaran yang bisa
dieksekusi, jadi tidak perlu lanjut mikirin data identitas apa yang mau dipakai buat daftar.

---

# BAGIAN 12 — DEMO CROSS-CHECK POLYGON: DETEKSI vs IZIN RESMI (14 Nov 2026)

## Tujuan
Membuktikan inti "inovasi" MineWatch secara konkret: area yang terdeteksi kehilangan vegetasi
(proxy gangguan tambang) di-overlay ke polygon izin resmi (BIG), untuk menunjukkan berapa %
area yang di LUAR izin yang berlaku (indikasi potensi pelanggaran).

## Data yang dipakai
- 3 lokasi RELIABLE dari hasil NDVI Syafa (BAGIAN 10): Kembar Emas Sultra, DAS Kampak (Bangka
  Barat), Laroenai (Morowali)
- Dataset BIG 4.608 polygon izin (`data/momi_processed/iup_izin_tambang_big_satupeta_merged.geojson`)
- Library: geopandas + rasterio + shapely (diinstall baru di sesi ini)

## Metodologi
1. Hitung NDVI before/after dari band B04/B08 asli (rasterio, pakai geotransform sebenarnya)
2. **Validasi silang**: angka "sharp NDVI loss pixel fraction" yang dihitung ulang di sini
   **PERSIS SAMA** dengan angka yang sudah dilaporkan Syafa (22,4% / 12,8% / 15,9%) — menegaskan
   perhitungan dasarnya konsisten dan bisa dipercaya.
3. Threshold piksel NDVI turun >0.2 -> polygonize (rasterio.features.shapes) jadi polygon vektor
   "area terdeteksi hilang vegetasi"
4. **PENTING — percobaan pertama (tanpa crop) GAGAL**: area merah menutupi hampir seluruh frame
   mengikuti pola garis pantai, bukan area tambang spesifik — kemungkinan noise dari pasang-surut/
   mangrove di citra pesisir, bukan sinyal tambang asli
5. **Perbaikan**: dipotong radius 3km dari titik kasus (koordinat dari laporan berita/Satgas PKH)
   sebelum overlay — hasilnya jauh lebih terlokalisir dan masuk akal secara visual
6. Overlay area terdeteksi (setelah crop) vs 5 polygon izin terdekat, hitung luas yang overlap
   vs di luar semua izin

## Hasil (radius 3km dari titik kasus)
| Lokasi | Area terdeteksi hilang vegetasi | Overlap dengan izin resmi | Di luar semua izin terdekat |
|---|---|---|---|
| Kembar Emas Sultra | 553 ha | 358 ha (65%) | **196 ha (35%)** |
| DAS Kampak, Bangka Barat | 374 ha | 113 ha (30%) | **261 ha (70%)** |
| Laroenai, Morowali | 592 ha | 284 ha (48%) | **308 ha (52%)** |

Visualisasi peta overlay (showcase): `analysis/polygon_crosscheck/kembar_emas_sultra_crosscheck_map_v2_clipped.png`
Data lengkap: `analysis/polygon_crosscheck/crosscheck_results_clipped_3km.json`,
`analysis/polygon_crosscheck/<kasus>_disturbance_polygons.geojson`

## CATATAN JUJUR WAJIB DIPATUHI (jangan disamarkan ke juri)
1. Ini **demo metodologi awal pakai threshold NDVI sederhana**, BUKAN model AI terlatih
   (U-Net/DeepLabV3+ yang direncanakan di arsitektur) — masih rawan salah tangkap noise non-tambang
   (awan, pasang-surut, variasi musiman vegetasi antar tahun 2018-2026).
2. Angka "% di luar izin" di atas adalah **ilustrasi mekanisme cross-check**, BUKAN vonis hukum
   dan BELUM tervalidasi lapangan — jangan diklaim sebagai "hasil deteksi AI yang akurat" ke juri
   tanpa embel-embel caveat ini.
3. Radius 3km dipilih secara heuristik (coba-coba) untuk mengurangi noise, BUKAN hasil dari
   batas administratif/geografis yang presisi — pendekatan produksi yang benar harus pakai
   boundary polygon izin itu sendiri sebagai AOI, bukan buffer radius generik.
4. Baru 1 dari 3 kasus yang divisualisasikan penuh (peta); 2 lainnya baru berupa angka tabel.
5. Pencarian "5 polygon izin terdekat" pakai jarak dari titik kasus — bisa saja melewatkan
   polygon izin relevan lain yang jaraknya >5 besar tapi overlap geometris (perlu ditingkatkan

## BAGIAN 13: Pelurusan Visi Produk + Rencana Training AI (14 Nov 2026)

### Visi produk final (dikonfirmasi user, menggantikan asumsi "threshold manual")
Dashboard baca citra satelit → diproses **AI TERLATIH** (bukan threshold manual) →
AI decide kandidat area tambang dengan confidence score → cross-check ke database izin
resmi (legal jika di dalam izin berlaku, **flagged for review** jika di luar/tanpa izin —
BUKAN vonis otomatis) → output ke dashboard analyst untuk human review → alert.
Ini konsisten dengan desain dashboard (ada tahap analyst review sebelum alert final).

### Keputusan strategi training
- 13 kasus ground-truth Indonesia (3 reliable secara NDVI) **DIREPOSISIKAN jadi
  TEST/VALIDATION SET**, bukan training set utama — jumlahnya terlalu sedikit untuk
  training from-scratch, risiko overfit & gampang tertipu noise (persis gejala yang
  kejadian di demo BAGIAN 12: threshold NDVI salah tangkap garis pantai/pasang-surut).
- Training corpus utama pakai dataset akademik besar + data negatif eksplisit (lihat
  tabel di bawah) supaya model settle dan tidak ketipu noise/pertanian/konstruksi.
- Output AI di-framing sebagai **"flagged for review"**, bukan vonis otomatis.
- Framing database izin (BIG hanya sampai ~2022; MOMI/MODI down & gated — lihat BAGIAN 11)
  disampaikan JUJUR ke juri sebagai keterbatasan, dengan roadmap 3 fase:
  Fase 1 (sekarang) = prototipe pakai snapshot publik BIG; Fase 2 (roadmap) = integrasi
  real-time via kerjasama resmi dengan Kementerian ESDM (opsi B2G, bisa dijual layanan);
  Fase 3 = rollout nasional. **Ditulis sebagai "designed for"/rencana, BUKAN klaim
  kerjasama yang sudah berjalan.**
- SAR (Sentinel-1) direposisikan jadi item Fase 2/roadmap mengingat timeline 3 bulan,
  kecuali Syafa punya bandwidth khusus.

### Dataset training yang sudah dikumpulkan (14 Nov 2026)
Lokasi: `data/training_datasets/` (total ~3,9 GB, disk sisa ~12 GB dari 31 GB — aman)

| Dataset | Fungsi | Ukuran | Status |
|---|---|---|---|
| **MineNetCD256** (HZDR-FWGEL, HuggingFace) | Training utama — 71.711 patch 256×256 bi-temporal siap pakai | 2,9 GB | ✅ lengkap |
| **Tang & Werner** (Zenodo 7894216) | 74.548 polygon tambang global (vektor), kolom `Name` = jenis tambang/komoditas | 296 MB | ✅ lengkap (didownload manual oleh Neil via Google Drive, diverifikasi 74.548 fitur terbaca) |
| **Jasansky et al.** (Zenodo 14195737) | Mask + bbox 1.210 lokasi, sudah split train/val/test, akurasi tervalidasi 99,78% (citra Sentinel-2 cuma referensi, belum termasuk) | 85 MB | ✅ lengkap (gpkg + referensi) |
| **Maus et al. v2** (PANGAEA 942325) | 44.929 polygon tambang global, metodologi beda dari Tang&Werner → cross-validasi | 24 MB | ✅ lengkap |
| **ESA WorldCover** tile S06E120 (Sulawesi) + S03E105 (Bangka) | Negatif: sawah, bangunan, pesisir/tidal — noise yang bikin demo BAGIAN 12 salah tangkap | 47 MB | ✅ lengkap (2 tile representatif, bukan full 117GB) |
| **Hansen Global Forest Change** v1.12, tile 00N_120E + 00N_100E (lossyear, treecover2000, datamask) | Konteks deforestasi tahunan — bedain "hutan hilang krn logging/pertanian" vs "krn tambang" | 569 MB | ✅ lengkap (2 tile Indonesia, bukan global) |
| **OSCD100** (HuggingFace) | Generic change-detection pretraining (bangunan/jalan baru, bukan tambang) — buat model belajar "definisi perubahan" dulu sebelum fine-tune | 220 MB | ✅ lengkap |
| **CloudSEN12+** (tacofoundation, HuggingFace) | Robustness terhadap awan — 50.247 sample metadata, **diakses via streaming on-demand** (`tacoreader.v1`), TIDAK didownload penuh (dataset asli ~1TB) | metadata only (~KB), sample individual ~beberapa MB saat dipanggil | ✅ terverifikasi bisa diakses, sampling aktual nanti pas bikin training pipeline |

**CATATAN RIWAYAT — Tang & Werner (Zenodo 7894216):**
Download otomatis dari environment ini gagal 4x (download browser otomatis maupun curl
langsung) — Zenodo memblokir curl dari IP environment ini (403 "unusual traffic"), dan
browser session berulang kali macet/terputus di tengah download file besar (>100MB,
diduga throttle/connection-reset dari jaringan environment ke CDN Zenodo). **Resolved**:
Neil download manual dari browser pribadinya, upload ke Google Drive, lalu ditarik ke
environment ini via `gdown` — berhasil, 74.548 fitur terverifikasi terbaca lengkap.

### Struktur training/val/test — FINAL (14 Nov 2026)
Dokumen lengkap: `data/training_datasets/DATASET_MANIFEST.md` — berisi peran tiap dataset,
skema terverifikasi (bukan asumsi dari deskripsi penerbit), dan rekomendasi split final.

Ringkasan temuan kunci dari inspeksi langsung:
- MineNetCD256 sudah punya split resmi (train 47.743 / val 4.613 / test 19.355), termasuk
  domain `Indonesia_01` (72 patch) — langsung relevan.
- **Class imbalance**: ~18-26% patch per split yang beneran ada perubahan (>1% piksel) — konsisten
  di semua split, jadi strategi training wajib pakai oversampling/weighted loss, bukan random sampling.
- Tang & Werner kolom `Name` **TIDAK RELIABLE** sebagai label jenis tambang (isinya mayoritas
  artefak digitasi GIS, bukan kode komoditas asli) — jangan dipakai buat klasifikasi jenis tambang.
- **Jasansky adalah satu-satunya sumber label jenis tambang yang reliable** (`minetype1`: Surface
  1.245/Placer 187/Brine&Evaporation 58/Underground 24), plus `test_polygons_validated` (116 polygon)
  = gold-standard benchmark eksternal penerbit (akurasi 99,78%).
- Script `scripts/dataset_loader.py` sudah dites jalan (CPU-only) — baca & decode batch dari
  MineNetCD256 train/val/test, siap dibungkus `torch.utils.data.Dataset` begitu training beneran
  dimulai di ModelArts.

### Catatan teknis penting untuk training
[KOREKSI 16 Nov 2026: paragraf di bawah ini SUDAH TIDAK BERLAKU — training dipindah dari
rencana ModelArts ke server lab lokal. Lihat BAGIAN 14 untuk status final & terkini.]
- ~~Tidak ada GPU di environment ini (VM 4-core CPU, QEMU virtual, no nvidia-smi/CUDA).
  Training model deep-learning (U-Net/DeepLabV3+) WAJIB di Huawei Cloud ModelArts.~~
- ~~Migrasi data lokal → ModelArts: via OBS (Object Storage Service), upload pakai
  `obsutil`...~~ — TIDAK JADI DIPAKAI, lihat BAGIAN 14.
- Riset referensi metodologi (BUKAN sumber data, repo cuma kode): paper "Multitemporal
  Spatial Analysis for Monitoring and Classification of Coal Mining and Reclamation
  Using Satellite Imagery" (MDPI rs17061090) — coal mining Tapin, Kalimantan Selatan,
  Sentinel-1 SAR + Sentinel-2, U-Net/ResNet, akurasi 97,4%. Bukti pendekatan SAR+optik
  fusion jalan untuk konteks Indonesia, tapi dataset asli tidak dipublikasikan.
   ke spatial join penuh kalau mau dipakai produksi).

---

# BAGIAN 14 — TRAINING PINDAH KE SERVER LAB LOKAL + PIPELINE END-TO-END (16 Nov 2026)

## Keputusan strategis: ModelArts → RTX 3060 lab lokal
Budget Huawei Cloud ModelArts terbatas, jadi training model dipindah ke server lab
Proxmox milik Neil (GPU RTX 3060 12GB) yang sudah di-setup environment-nya. **OBS dan
ECS tetap dipertahankan/provisioned** sebagai bukti penggunaan layanan Huawei Cloud —
klarifikasi kriteria penilaian kompetisi: TIDAK wajib full-run di layanan mereka, cukup
memanfaatkan salah satu.
[UPDATE 17 Nov 2026: ModelArts di-drop TOTAL dari scope, bukan cuma dari jalur training
aktual — fix final cuma 2 layanan: OBS + ECS. Entry Form resmi sudah konsisten dengan ini
sejak awal (nggak pernah menyebut ModelArts).]

## Spek container training (`kulonuwun`, LXC privileged di Proxmox)
- IP `172.20.0.160`, akses SSH key-only (bukan password)
- GPU: **NVIDIA RTX 3060, 12.49GB VRAM**, driver 595.91.07, CUDA max 13.2
- RAM 12GB (12288 MiB), Swap 8GB, vCPU 8, Disk 137GB (60GB OS + ~140GB data/kerja)
- Environment: Python 3.10.12, **PyTorch 2.5.1+cu121** (`cuda.is_available()=True`),
  GDAL 3.4.1, rasterio 1.4.4, geopandas 1.1.4

## Dataset di-transfer, bukan di-rebuild di remote
Seluruh `data/` (4,7GB, 337 file — MineNetCD256 + 13 lokasi pilot Sentinel-2 + izin BIG)
dan `scripts/`, `docs/`, `analysis/` disinkronkan via `rsync` ke `/opt/minewatch/project/`
di container. Checksum lokal vs remote dicocokkan (4,7GB/337 file persis sama).

## Perbaikan kode penting di sesi ini
1. **`scripts/dataset_loader.py`** — ditulis ulang: dari `pd.read_parquet()` (load penuh ke
   pandas DataFrame, BERMASALAH dengan `DataLoader(num_workers>0)` karena duplikasi
   memory per worker lewat fork+refcounting) jadi `pyarrow.parquet.read_table()` + slice
   per-row saat `__getitem__` (fork-safe, arrow buffer di luar Python heap). Class
   `TorchMineNetCD(Dataset)` dipindah ke sini jadi satu lokasi kanonik (sebelumnya
   duplikat di `train.py`).
2. **`scripts/train_production.py`** (baru) — training loop produksi, beda dari
   `train.py` (smoke test doang): mixed precision (AMP, `torch.amp.autocast`+`GradScaler`
   — RTX 3060 Ampere punya tensor core), `pin_memory=True`, `num_workers=4`, train/val
   split proper, checkpoint model TERBAIK (berdasar val_loss bukan train_loss),
   early stopping (patience), LR scheduler `ReduceLROnPlateau`.
3. **`scripts/evaluate.py`** (baru) — metrik segmentasi standar (IoU, F1, Precision,
   Recall) di test split — sebelumnya cuma ada angka loss yang kurang informatif
   buat laporan/demo ke juri.
4. **`scripts/inference_pipeline.py`** (baru) — pipeline END-TO-END pertama yang
   benar-benar nyambungin GeoTIFF mentah → tiling 256×256 → inference model →
   vectorize mask jadi polygon → `permit_crosscheck.crosscheck()`. Ini yang
   dijanjikan di flowchart arsitektur/poster, baru di sesi ini dites jalan beneran.
   Nemu & benerin bug lama di `permit_crosscheck.py`: path database izin
   (`IUP_GLOB`) di-hardcode relatif ke cwd pemanggil — dibikin absolut relatif ke
   lokasi file modul, supaya robust dipanggil dari direktori mana pun.

## Eksperimen base_ch: 32 dipilih dulu, divalidasi real (bukan tebakan)
Sempat ragu antara `base_ch=32` vs `64` (kapasitas model). Diputuskan mulai dari 32
(risiko VRAM lebih rendah, waktu lebih predictable), TAPI setelah diukur pakai VRAM
probe sintetis (forward+backward dummy tensor, tanpa data asli):
- base_ch=32, batch=8 → cuma 1,25GB VRAM (jauh di bawah 12GB kapasitas)
- **base_ch=64, batch=16 → 4,94GB VRAM, TERNYATA AMAN** (awalnya dikira berisiko OOM)
Kesimpulan: base_ch=64 lebih worth dicoba daripada sekadar naikin batch_size (batch
besar di base_ch=32 TIDAK menaikkan throughput signifikan — GPU sudah compute-saturated
di batch kecil, dibuktikan lewat speed probe ~48-50 patch/detik stabil di base_ch=32
berapa pun batch size-nya).

## Status training saat ini (16 Nov 2026) — SUDAH SELESAI, hasil final lihat BAGIAN 15
- **v1**: base_ch=32, batch=8, AMP aktif, 4 worker. Epoch 1-3 selesai, val_loss turun
  konsisten (0,0319 → 0,0305 → 0,0285), ~492-521 detik/epoch. Checkpoint tersimpan di
  `checkpoints/production_v1/best_model.pt`.
- **v2** (antrian otomatis, lewat watcher `chain_v2.sh`): begitu v1 selesai/early-stop,
  langsung lanjut base_ch=64, batch=16, tanpa jeda nganggur GPU.
- Checkpoint epoch-3 v1 sudah dites lewat `evaluate.py` (IoU 0,38, F1 0,55) dan
  `inference_pipeline.py` (kasus Kembar Emas Sultra: 2.137,5 ha terdeteksi, 549,4 ha/
  25,7% di luar izin — ballpark sama dengan analisis NDVI/NDMI manual BAGIAN 12,
  masuk akal untuk model yang baru 3 epoch, BELUM final).

## Hubungan Task 4 (47 lokasi Jasansky Indonesia) dengan training — PENTING, sering disalahpahami
[STATUS 17 Nov 2026: Task 4 DIHIDUPKAN LAGI lewat jalur STAC (BAGIAN 15). Sub-bagian
"DIHENTIKAN" di bawah dipertahankan sebagai sejarah KENAPA jalur browser ditinggalkan —
BUKAN status sekarang.]
Task 4 **TIDAK dipakai sebagai training data v1/v2/v3** — v1/v2/v3 training HANYA pakai
MineNetCD256 (split resmi, tidak menyentuh data Jasansky sama sekali). Tujuan ASLI Task 4
(dikonfirmasi dari kolom `split` di geopackage sumber Jasansky — 47/47 lokasi berasal dari
split "train"): menambah data training domain-spesifik Indonesia (MineNetCD256 cuma
punya 72 dari 71.711 patch bertag "Indonesia_01"), bukan sekadar kasus demo. Realisasinya
= training run **v4** (lihat BAGIAN 15).

## [SEJARAH] Status Task 4 per 16 Nov 2026 sore — jalur BROWSER dihentikan
Keputusan: **Task 4 tidak dilanjutkan**, berdasarkan bukti nyata dari pilot test (bukan
dugaan), karena efisiensi biaya-vs-manfaat tidak masuk akal:

**Masalah teknis nyata yang ditemukan (pilot test tile_id 2168, lokasi placer/artisanal
Kalimantan):**
1. Dataset Jasansky itu **single-date per lokasi** (cuma 1 `s2_tile_id` + tanggal, bukan
   pasangan before/after) — harus cari sendiri citra "before" yang valid, tidak ada
   jawaban baku tanggal berapa.
2. Setup akses: TIDAK ada jalur API resmi tanpa password manual (OAuth client_credentials
   butuh password yang cuma ada di vault, tidak bisa diekstrak ke kode) — satu-satunya
   jalur adalah klik UI Copernicus Browser manual.
3. Preview kecil di UI Copernicus Browser **tidak reliable** untuk cek awan/nodata (sudah
   tercatat sebagai pitfall umum) — kandidat "before" pertama (2017-07-25) yang di preview
   terlihat OK, setelah didownload full-res ternyata **60% nodata** (celah antar-swath
   satelit) + sisanya berawan. Harus download dulu baru bisa pastikan valid.
4. Setelah beberapa kali request download berturut-turut, **tombol Download berhenti
   merespons** (>70 detik tanpa hasil, tidak ada pesan error) — diduga rate-limit akun
   Copernicus free-tier, tidak ada cara pasti untuk konfirmasi/mengatasi tanpa trial lebih
   lanjut.
5. Sesi browser (SPA Copernicus) crash/logout 3× selama 1 sesi percobaan, masing-masing
   butuh re-login manual via vault.

**Biaya vs manfaat:** 1 lokasi (before+after tervalidasi) butuh >60 tool-call dan BELUM
berhasil tuntas dalam 1 sesi percobaan penuh. Diekstrapolasi ke 47 lokasi: berjam-jam kerja
manual dengan hasil tidak pasti (tergantung rate-limit), untuk manfaat yang marginal (47
patch tambahan vs 47.743 patch MineNetCD256 yang sudah dipakai v1/v2).

**Dampak ke model final:** TIDAK ADA dampak ke training v1/v2 yang sedang berjalan (tidak
pernah bergantung pada Task 4). Model akhir dilatih murni di MineNetCD256 (dataset
change-detection global). Framing untuk laporan kompetisi: "model dilatih di dataset
change-detection global (MineNetCD256); fine-tuning domain-spesifik Indonesia
diidentifikasi sebagai future work" — pendekatan standar & jujur untuk prototipe 3 bulan,
bukan kekurangan yang disembunyikan.

**Arsip percobaan:** file yang sempat berhasil didownload selama pilot test disimpan di
`data/sentinel2_jasansky/` sebagai dokumentasi proses, DITANDAI jelas tidak dipakai di
training (lihat `data/sentinel2_jasansky/README_TIDAK_DIPAKAI.md`).

# BAGIAN 15 — HASIL v1/v2, DIAGNOSIS OVERFITTING, PAKET REGULARISASI v3, TASK 4 HIDUP LAGI VIA STAC, RANTAI v3→v4 (16–17 Nov 2026)

## 15.1 Hasil final training v1 dan v2 (MEASURED, evaluasi pixel-level di split `test` MineNetCD256)
| Run | base_ch | Params | Best epoch / stop | IoU | F1 | Precision | Recall |
|---|---|---|---|---|---|---|---|
| v1 `production_v1` | 32 | 1,93 jt | 14 / 24 | 0,383 | 0,554 | 0,448 | 0,727 |
| v2 `production_v2_base64` | 64 | 7,70 jt | 12 / 20 | **0,411** | **0,582** | 0,488 | 0,721 |

- Keduanya early-stop (patience 8) dengan best val_loss IDENTIK 0,0228 — val_loss saja tidak
  bisa bedain model; evaluasi test-set terpisah yang nunjukin v2 unggul.
- **Diagnosis: overfitting, bukun undertraining.** Bukti v1 epoch 14→24: train_loss
  0,0253→0,0181 turun terus, val_loss 0,0228→0,0247 naik. Kode v1/v2 memang NOL augmentasi,
  dropout, maupun weight decay. Pola yang sama di v2.
- v2 = model final sementara sampai v3/v4 dievaluasi.

## 15.2 Paket regularisasi v3 (sudah diimplementasi, py_compile OK, smoke-test di GPU lab)
Sekarang jadi DEFAULT CLI `scripts/train_production.py`. Perilaku v1/v2 tetap reproducible via
`--dropout 0 --loss focal --scheduler plateau --ema-decay 0 --lr 1e-3 --patience 8`.
1. Augmentasi geometri (flip H/V, rot90) + fotometrik (kontras/brightness ±10%, noise; faktor
   SAMA ke before & after supaya nggak menciptakan "perubahan palsu") — train only.
2. `AdamW(weight_decay=1e-4)`.
3. `Dropout2d` di `model.py`: bottleneck-diff 0,3, dec3 0,3, dec2 0,15 (default 0 = Identity →
   checkpoint v1/v2 tetap load `strict=True`, `evaluate.py`/`inference_pipeline.py` tak berubah).
4. Loss `FocalDiceLoss` = 0,5·Focal(α 0,75, γ 2) + 0,5·Dice (Dice dihitung fp32 di bawah AMP).
5. lr 3e-4, warmup 2 epoch + cosine, patience 12, EMA bobot 0,999 dengan ramp-up timm-style;
   val & checkpoint pakai bobot EMA. `config.json` disimpan tiap run.
Smoke (MEASURED): base_ch 64, 3 epoch, 400/160 patch, ~11,7 s/epoch, val_loss 0,465→0,431→0,445,
tanpa NaN. Catatan jujur: 5 perubahan sekaligus → kalau v3 lebih bagus, kontribusi
masing-masing TIDAK diketahui (ablation hanya kalau GPU nganggur).

## 15.3 Task 4 HIDUP LAGI — jalur STAC Planetary Computer, bukan browser
`scripts/jasansky_stac_download.py` (jalan di container lab): ambil produk Sentinel-2 L2A
PERSIS sesuai `s2_tile_id` Jasansky (ID item PC == ID produk ESA) dari STAC Microsoft
Planetary Computer, windowed read bbox tile (~2048² px @10 m), band B02/B03/B04/B08 uint16 +
SCL, rasterize `preferred_polygons` → `label_polygon_mask.tif`. BEFORE = kandidat PALING
AWAL (arsip 2015-07 → after−180 hari, cloud<50) yang lolos nodata ≤5% & awan-di-polygon
≤10%, fallback paling bersih ≤35%. Pre-screen pakai SCL doang (hemat bandwidth). Output
`data/sentinel2_jasansky_stac/tile_<id>/`, `manifest.json` resumable. ~1,5–2 menit/tile
(MEASURED pilot 2168 = 95 s). Tanpa login, tanpa tombol download, tanpa tab crash.
Status 17 Nov 01:10 WIB: 29/47 diproses (19 done, 5 "excluded" = before sudah tambang,
3 failed), batch masih jalan.

## 15.4 Label & aturan exclude Jasansky — DUA keputusan penting
- **Polygon Jasansky TIDAK boleh dipakai mentah sebagai label piksel.** Ketahuan dari cek
  visual triptych (angka QA semua terlihat sehat): polygon itu blob kasar yang nyakup hutan/
  kebun → model diajarin "hutan = tambang". Label turunan (`jasansky_build_patches.py`):
  di dalam polygon ∧ NDVI_before ≥ 0,3 ∧ NDVI_after < 0,3 ∧ SCL valid dua tanggal; blob
  < 50 px dibuang.
- **Aturan "before sudah tambang → tile dibuang" (16 Nov) DIGANTI oleh Neil 17 Nov dini
  hari → tile itu DIPAKAI sebagai contoh EKSPANSI.** Dengan label turunan, pit lama otomatis
  0 dan hanya bukaan baru 1 — konsisten dengan arti label MineNetCD (perubahan antar dua
  tanggal). Alasan: aturan lama buang 12/14 tile (arsip S2 mulai pertengahan 2015, mayoritas
  lokasi artisanal udah terbuka — batas fisik arsip). Yield aturan ekspansi: 20/23 tile,
  1.198 patch, 416 positif (uji 17 Nov). Exclude sekarang hanya: tak ada tambang terlihat di
  after (<2000 px) atau ekspansi terlalu kecil (<2000 px). `preexisting_frac` tetap dicatat.
- Noise residual yang diakui: land-clearing kebun di dalam polygon kasar ikut terlabel
  ekspansi (terlihat di tile 2168). Jangan disembunyikan ke juri.
- QA per-patch 256²: nodata ≤2%, awan (SCL 3/8/9/10) ≤10% di KEDUA tanggal. SCL kelas 7
  (unclassified) sengaja TIDAK dihitung awan (di tropis nutupin 80% patch).
- Format output parquet IDENTIK MineNetCD256 (`imageA/imageB/label` PNG, `domain` =
  `Indonesia_jasansky_<tile>`). Split **PER-LOKASI** 75/25 (seed 42), dihitung SETELAH
  exclude: `jasansky_train` (masuk v4 via `MINEWATCH_INCLUDE_JASANSKY=1`) dan `jasansky_val`
  (held-out "lokasi Indonesia yang belum pernah dilihat" — dipakai evaluasi v2/v3/v4).
  `dataset_loader.py` & `evaluate.py` sudah kenal kedua split.

## 15.5 Rantai otomatis malam 17 Nov (`scripts/chain_v3_overnight.sh`, jalan di lab)
Download selesai → build patch (split 75/25) → **v3** = MineNetCD saja + regularisasi,
base_ch 64, **epochs 50**, patience 12 → eval v2 & v3 di `test` (subset 2000) dan `jasansky_val`
→ **v4** = config v3 + `jasansky_train`, **epochs 50** → eval v4 di kedua split. Status di
`/tmp/chain_v3.status`, log `/tmp/chain_v3.log`, training log `/tmp/production_v3.log`,
`/tmp/production_v4.log`. Cron Telegram tiap 2 jam cuma baca status (tidak memutuskan apa pun).
Keputusan Neil: epoch TETAP 50, base_ch TETAP 64 (tawaran cap 35 epoch / base_ch 48 ditolak).
**STATUS 18 Nov 2026 01:24 WIB: chain SELESAI (status DONE). Hasil final lihat 15.8.**

## 15.8 HASIL FINAL v1–v4 (MEASURED, 18 Nov 2026) — v4 menang telak di kedua split
v3 early-stop epoch 40/50 (best val_loss 0,3877); v4 early-stop epoch 38/50, checkpoint
terbaik epoch 26 (best val_loss 0,3888). **Bug chain**: proses v3 segfault saat exit
(rc=139) — checkpoint TETAP valid (sudah "Selesai" + tersimpan), tapi chain's naive
`rc!=0 -> GAGAL` check men-skip eval otomatis v3 (lihat pitfall "segfault during CUDA-context
teardown" di skill). Eval v2 & v3 dijalankan manual untuk melengkapi tabel ini.

**Split `test` (2000 patch, benchmark global MineNetCD256):**
| Run | IoU | F1 | Precision | Recall |
|---|---|---|---|---|
| v1 | 0,383 | 0,554 | 0,448 | 0,727 |
| v2 | 0,411 | 0,582 | 0,488 | 0,721 |
| v3 (regularisasi) | 0,430 | 0,602 | 0,539 | 0,681 |
| **v4 (+ data Indonesia)** | **0,438** | **0,609** | 0,566 | 0,660 |

**Split `jasansky_val` (120 patch, 8 lokasi Indonesia held-out, belum pernah dilihat training):**
| Run | IoU | F1 | Precision | Recall |
|---|---|---|---|---|
| v2 | 0,112 | 0,202 | 0,128 | 0,474 |
| v3 | 0,175 | 0,297 | 0,215 | 0,482 |
| **v4** | **0,360** | **0,530** | 0,485 | 0,584 |
(v1 tidak pernah dites di split ini — split baru dibuat bareng v3/v4, jangan dikarang.)

**Kesimpulan: v4 adalah model final/terbaik di KEDUA split.** Di benchmark global
peningkatan v1→v4 bertahap (overfitting-fix + data Indonesia nambah dikit-dikit). Di lokasi
Indonesia yang belum pernah dilihat, IoU v4 (0,360) lebih dari **2x lipat** v3 (0,175) —
bukti kuat bahwa menambah data Jasansky Indonesia ke training (v4) benar-benar memperbaiki
generalisasi ke lokasi lokal, bukan cuma noise. Checkpoint final:
`checkpoints/production_v4_base64_reg_jasansky/best_model.pt`.

## 15.6 Desain eksperimen & framing kompetisi
- v2 vs v3 (sama-sama MineNetCD saja) = efek regularisasi. v3 vs v4 = efek data domain
  Indonesia. Keduanya diukur di `test` global DAN `jasansky_val` Indonesia held-out.
- Klaim yang boleh dipakai kalau angkanya mendukung: "dilatih di benchmark global + 25
  lokasi Indonesia (jasansky_train, 25 tile/432 patch), diuji di 8 lokasi Indonesia yang
  belum pernah dilihat (jasansky_val, 120 patch)" — HASIL MENDUKUNG klaim ini (lihat 15.8).
- Jasansky split=='test' (116 tile) TETAP tidak disentuh.

## 15.7 File yang relevan
`scripts/{model.py, dataset_loader.py, train_production.py, evaluate.py,
jasansky_stac_download.py, jasansky_build_patches.py, chain_v3_overnight.sh}` (tersinkron ke
`/opt/minewatch/project/scripts/`), `docs/Panduan_Download_Jasansky.pdf` (panduan manual
browser — sekarang cuma cadangan), `data/sentinel2_jasansky/` = arsip jalur browser, TIDAK
dipakai. Detail operasional (pitfall, perintah) ada di skill `huawei-ict-mining-competition`.
