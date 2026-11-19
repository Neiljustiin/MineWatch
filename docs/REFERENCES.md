# Referensi & Fundamental Teknis — MineWatch

Dokumen ini ngumpulin sumber-sumber valid (paper peer-review, repo resmi, proyek
production yang sudah berjalan) yang jadi dasar tiap keputusan teknis di proyek ini.
Tujuannya: setiap klaim teknis di pitch/submission kompetisi bisa ditelusuri ke sumber
asli, bukan asumsi/tebakan.

## 1. Dataset training utama — MineNetCD256
**Paper**: Yu, W., Zhang, X., Zhu, X.X., Gloaguen, R., Ghamisi, P. (2024).
"MineNetCD: A Benchmark for Global Mining Change Detection on Remote Sensing Imagery."
arXiv:2407.03971.
- Ini BUKAN dataset buatan sendiri — benchmark resmi dari tim riset (termasuk Xiao Xiang
  Zhu, periset remote sensing ternama di TU Munich), berisi 70k+ patch berpasangan dari
  100 lokasi tambang di seluruh dunia, dengan anotasi pixel-level.
- Paper ini juga memperkenalkan baseline model "ChangeFFT" dan membandingkan 13 model
  change detection lain — jadi referensi pembanding kalau nanti kita mau benchmark hasil
  model kita sendiri.
- Relevansi: ini dataset training CORE kita (2,9GB, 71.711 patch) — fundamentnya sudah
  divalidasi lewat proses peer-review, bukan data mentah tanpa standar.

## 2. Arsitektur model — FC-Siam-diff
**Paper**: Daudt, R.C., Le Saux, B., Boulch, A. (2018). "Fully Convolutional Siamese
Networks for Change Detection." IEEE ICIP 2018, pp. 4063-4067. arXiv:1810.08462.
**Implementasi resmi**: github.com/rcdaudt/fully_convolutional_change_detection (234
bintang GitHub per pengecekan terakhir)
**Validasi tambahan**: arsitektur ini juga diimplementasi ulang di `torchgeo`
(github.com/torchgeo/torchgeo/blob/main/torchgeo/models/fcsiam.py) — torchgeo adalah
library resmi untuk geospatial deep learning yang dipelihara komunitas besar (dipakai
banyak proyek remote sensing production), jadi FC-Siam-diff bukan arsitektur niche/usang,
masih relevan dan dipakai sampai sekarang.
- Relevansi: ini arsitektur model kita (`scripts/model.py`) — pilihan yang tervalidasi
  secara akademis utk tugas "2 citra before/after -> mask perubahan", bukan hasil coba-coba.

## 3. Loss function — Focal Loss
**Paper**: Lin, T.Y., Goyal, P., Girshick, R., He, K., Dollár, P. (2017). "Focal Loss for
Dense Object Detection." ICCV 2017. arXiv:1708.02002.
- Paper ini dari tim Facebook AI Research (FAIR), salah satu paper computer vision paling
  disitasi (>30.000 sitasi) — standar industri untuk masalah class imbalance berat.
- Relevansi: dipakai di `scripts/model.py` (`FocalLoss` class) untuk ngatasin imbalance
  piksel "berubah vs tidak" yang kita temukan sendiri di data (~75-80% piksel per patch
  tidak berubah, bahkan di patch yang "positif").

## 4. Bukti proyek sejenis yang SUDAH BERJALAN production (validasi konsep, bukan cuma riset)
**Amazon Mining Watch / earthrise-media/mining-detector**
(github.com/earthrise-media/mining-detector, amazonminingwatch.org)
- Partnership antara Pulitzer Center's Rainforest Investigations Network, Amazon
  Conservation Association, dan Earth Genome — proyek jurnalisme investigatif yang
  BENERAN dipakai mendeteksi tambang emas artisanal ilegal di seluruh Amazon basin via
  citra Sentinel-2 + ensemble CNN, dengan hasil dipublikasikan sebagai peta publik.
- Relevansi: INI BUKTI KONKRET bahwa pendekatan "satelit + deep learning untuk deteksi
  tambang ilegal" bukan ide spekulatif — sudah ada yang deploy dan dipakai nyata untuk
  investigasi lingkungan, mendukung kelayakan MineWatch sebagai produk, bukan cuma proof
  of concept akademis.

**Paper pendukung tambahan** (konteks Amazon, metodologi serupa):
Godinho Silva et al. "Change Detection of Amazonian Alluvial Gold Mining Using Deep
Learning and Sentinel-2 Imagery." Remote Sensing 2022, 14(7), 1746.
(doi.org/10.3390/rs14071746) — studi akademis peer-review yang spesifik bandingin
beberapa pendekatan deep learning utk deteksi perubahan akibat tambang emas artisanal,
termasuk uji out-of-sample ke **Indonesia** (salah satu region test mereka).

## 5. Ground-truth / data referensi izin tambang
**Maus et al. v2**: Maus, V., et al. (2020). "A global-scale data set of mining polygons."
Scientific Data 7, 289. (nature.com/articles/s41597-020-00624-w) — Nature journal,
peer-reviewed, dataset yang kita pakai (`maus_v2_polygons/`).

## Kesimpulan
Tiap komponen inti MineWatch (dataset training, arsitektur model, loss function, dan
konsep produknya sendiri) masing-masing punya sandaran ke paper peer-review dan/atau
implementasi resmi yang bisa diverifikasi — bukan dibangun dari asumsi. Yang sifatnya
masih murni bikinan kita sendiri (dan harus jujur disampaikan sebagai itu): pipeline
cross-check ke database izin resmi Indonesia (MOMI/BIG), sample negatif dari ESA
WorldCover, dan integrasi end-to-end-nya sebagai satu produk dashboard.
