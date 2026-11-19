"""
Arsitektur model change detection: FC-Siam-diff.

Referensi: Daudt, R.C., Le Saux, B., Boulch, A. (2018) "Fully Convolutional
Siamese Networks for Change Detection", ICIP 2018 (arXiv:1810.08462).
Dipilih karena ini arsitektur published & tervalidasi khusus untuk tugas
"2 citra (before/after) -> mask perubahan", bukan arsitektur hasil tebakan.

Cara kerja singkat:
- 1 encoder (bobot SAMA/shared) dipakai buat nge-encode imageA dan imageB
  secara terpisah -> menghasilkan feature pyramid untuk masing-masing.
- Di tiap level resolusi, fitur A dan B dibandingkan pakai |A - B| (absolute
  difference) -> ini sinyal "seberapa beda" di titik itu.
- Decoder (mirip U-Net) naikin resolusi bertahap, gabungin sinyal beda dari
  tiap level (skip connection), lalu keluarin 1 channel logit per pixel
  (256x256) = peta probabilitas "piksel ini berubah/tidak".

Model ini SENGAJA dibikin ringan (channel kecil) supaya bisa di-smoke-test
di CPU biasa tanpa GPU -- bukan ukuran final buat training beneran di
ModelArts (nanti channel-nya dinaikin begitu ada GPU).
"""
import torch
import torch.nn as nn
import torch.nn.functional as F


def conv_block(in_ch, out_ch):
    return nn.Sequential(
        nn.Conv2d(in_ch, out_ch, 3, padding=1),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
        nn.Conv2d(out_ch, out_ch, 3, padding=1),
        nn.BatchNorm2d(out_ch),
        nn.ReLU(inplace=True),
    )


class SharedEncoder(nn.Module):
    """Encoder yang dipakai bersama (shared weights) untuk imageA & imageB."""

    def __init__(self, base_ch=16):
        super().__init__()
        self.enc1 = conv_block(3, base_ch)          # 256x256
        self.enc2 = conv_block(base_ch, base_ch * 2)      # 128x128
        self.enc3 = conv_block(base_ch * 2, base_ch * 4)  # 64x64
        self.bottleneck = conv_block(base_ch * 4, base_ch * 8)  # 32x32
        self.pool = nn.MaxPool2d(2)

    def forward(self, x):
        f1 = self.enc1(x)                  # 256x256, base_ch
        f2 = self.enc2(self.pool(f1))       # 128x128, base_ch*2
        f3 = self.enc3(self.pool(f2))       # 64x64, base_ch*4
        f4 = self.bottleneck(self.pool(f3))  # 32x32, base_ch*8
        return f1, f2, f3, f4


class FCSiamDiff(nn.Module):
    """FC-Siam-diff: shared encoder + absolute-diff skip connections + decoder.

    dropout: Dropout2d (matiin seluruh channel) di bottleneck-diff dan 2 blok
    decoder terdalam. Ditambah 16 Nov 2026 sebagai regularisasi anti-overfitting
    (v1/v2 overfit mulai epoch ~14 tanpa regularisasi sama sekali). Default 0.0
    biar checkpoint v1/v2 lama tetap bisa di-load tanpa perubahan perilaku.
    """

    def __init__(self, base_ch=16, num_classes=1, dropout=0.0):
        super().__init__()
        self.encoder = SharedEncoder(base_ch)
        self.drop_bottleneck = nn.Dropout2d(dropout) if dropout > 0 else nn.Identity()
        self.drop_dec3 = nn.Dropout2d(dropout) if dropout > 0 else nn.Identity()
        self.drop_dec2 = nn.Dropout2d(dropout / 2) if dropout > 0 else nn.Identity()

        self.up3 = nn.ConvTranspose2d(base_ch * 8, base_ch * 4, 2, stride=2)
        self.dec3 = conv_block(base_ch * 8, base_ch * 4)  # concat diff3 (base_ch*4) + up (base_ch*4)

        self.up2 = nn.ConvTranspose2d(base_ch * 4, base_ch * 2, 2, stride=2)
        self.dec2 = conv_block(base_ch * 4, base_ch * 2)

        self.up1 = nn.ConvTranspose2d(base_ch * 2, base_ch, 2, stride=2)
        self.dec1 = conv_block(base_ch * 2, base_ch)

        self.out_conv = nn.Conv2d(base_ch, num_classes, kernel_size=1)

    def forward(self, image_before, image_after):
        a1, a2, a3, a4 = self.encoder(image_before)
        b1, b2, b3, b4 = self.encoder(image_after)

        diff1 = torch.abs(a1 - b1)
        diff2 = torch.abs(a2 - b2)
        diff3 = torch.abs(a3 - b3)
        diff4 = torch.abs(a4 - b4)

        x = self.up3(self.drop_bottleneck(diff4))
        x = self.drop_dec3(self.dec3(torch.cat([x, diff3], dim=1)))

        x = self.up2(x)
        x = self.drop_dec2(self.dec2(torch.cat([x, diff2], dim=1)))

        x = self.up1(x)
        x = self.dec1(torch.cat([x, diff1], dim=1))

        logits = self.out_conv(x)  # (B, 1, 256, 256)
        return logits


class FocalLoss(nn.Module):
    """
    Focal loss (Lin et al., 2017) untuk binary segmentation dengan class
    imbalance berat -- di dataset kita, bahkan di patch yang "ada perubahan",
    mayoritas piksel tetap "tidak berubah" (perubahan biasanya cuma area kecil
    di tengah patch). BCE biasa gampang didominasi kelas mayoritas.
    """

    def __init__(self, alpha=0.75, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits, target):
        bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none")
        p = torch.sigmoid(logits)
        p_t = p * target + (1 - p) * (1 - target)
        alpha_t = self.alpha * target + (1 - self.alpha) * (1 - target)
        focal = alpha_t * (1 - p_t) ** self.gamma * bce
        return focal.mean()


class DiceLoss(nn.Module):
    """Soft Dice loss -- langsung ngoptimasi overlap prediksi vs label (~IoU).
    Dihitung per-batch (bukan per-sample) biar stabil di patch yang labelnya
    kosong/hampir kosong."""

    def __init__(self, smooth=1.0):
        super().__init__()
        self.smooth = smooth

    def forward(self, logits, target):
        p = torch.sigmoid(logits)
        inter = (p * target).sum()
        denom = p.sum() + target.sum()
        return 1.0 - (2.0 * inter + self.smooth) / (denom + self.smooth)


class FocalDiceLoss(nn.Module):
    """Kombinasi Focal + Dice (16 Nov 2026).

    Alasan: FocalLoss sendirian di v1/v2 ngasih recall tinggi (0.72) tapi
    precision rendah (0.49) -> over-detect. Dice ngarahin optimasi langsung ke
    overlap (metrik yang kita nilai: IoU/F1), ngebantu precision tanpa
    ngorbanin recall banyak. Bobot 0.5/0.5 = default umum di literatur
    segmentasi medis/remote sensing; bukan hasil tuning di data kita.
    """

    def __init__(self, alpha=0.75, gamma=2.0, dice_weight=0.5):
        super().__init__()
        self.focal = FocalLoss(alpha=alpha, gamma=gamma)
        self.dice = DiceLoss()
        self.dice_weight = dice_weight

    def forward(self, logits, target):
        # Dice dihitung di fp32 biar aman di bawah AMP (sum besar di fp16 bisa overflow)
        return (1 - self.dice_weight) * self.focal(logits, target) \
            + self.dice_weight * self.dice(logits.float(), target.float())


if __name__ == "__main__":
    # Smoke test paling dasar: cuma cek forward pass jalan & shape benar,
    # TANPA load dataset asli -- buat verifikasi arsitektur doang.
    model = FCSiamDiff(base_ch=16)
    n_params = sum(p.numel() for p in model.parameters())
    dummy_a = torch.randn(2, 3, 256, 256)
    dummy_b = torch.randn(2, 3, 256, 256)
    out = model(dummy_a, dummy_b)
    print(f"Model params: {n_params:,}")
    print(f"Output shape: {tuple(out.shape)} (expected (2, 1, 256, 256))")
    assert out.shape == (2, 1, 256, 256), "Shape output salah!"
    print("OK — arsitektur FC-Siam-diff jalan, forward pass sukses.")
