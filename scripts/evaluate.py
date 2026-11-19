"""
Evaluasi model change detection pakai metrik standar (bukan cuma loss):
IoU, F1, Precision, Recall -- level pixel, dihitung di test split (data yang
nggak pernah keliat model selama training ATAU validation).

Loss doang nggak informatif buat laporan/demo kompetisi -- reviewer/judge
biasanya nanya "IoU berapa" atau "F1 berapa", bukan "focal loss berapa".

CARA PAKAI:
    python3 evaluate.py --checkpoint ../checkpoints/<run_name>/best_model.pt
"""
import argparse
import sys
import os

import torch
from torch.utils.data import DataLoader

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dataset_loader import TorchMineNetCD  # noqa: E402
from model import FCSiamDiff  # noqa: E402

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _collate(batch):
    return (
        torch.stack([b[0] for b in batch]),
        torch.stack([b[1] for b in batch]),
        torch.stack([b[2] for b in batch]),
    )


@torch.no_grad()
def evaluate(checkpoint_path, split="test", batch_size=16, threshold=0.5, subset_size=None):
    ckpt = torch.load(checkpoint_path, map_location=DEVICE, weights_only=False)
    base_ch = ckpt["base_ch"]
    model = FCSiamDiff(base_ch=base_ch).to(DEVICE)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    print(f"=== Evaluasi model (base_ch={base_ch}, checkpoint epoch={ckpt.get('epoch', '?')}, "
          f"val_loss saat training={ckpt.get('val_loss', float('nan')):.4f}) ===")
    print(f"Split: {split} | threshold: {threshold} | device: {DEVICE}")

    ds = TorchMineNetCD(split, subset_size=subset_size)
    loader = DataLoader(ds, batch_size=batch_size, shuffle=False, num_workers=2, collate_fn=_collate)
    print(f"Jumlah patch: {len(ds)}")

    tp = fp = fn = tn = 0

    for img_a, img_b, label in loader:
        img_a, img_b = img_a.to(DEVICE), img_b.to(DEVICE)
        label = label.to(DEVICE)

        logits = model(img_a, img_b)
        pred = (torch.sigmoid(logits) > threshold).float()
        gt = (label > 0.5).float()

        tp += ((pred == 1) & (gt == 1)).sum().item()
        fp += ((pred == 1) & (gt == 0)).sum().item()
        fn += ((pred == 0) & (gt == 1)).sum().item()
        tn += ((pred == 0) & (gt == 0)).sum().item()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    iou = tp / (tp + fp + fn) if (tp + fp + fn) > 0 else 0.0
    pixel_acc = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0.0

    print(f"\n--- Hasil evaluasi pixel-level ({split} split, {len(ds)} patch) ---")
    print(f"IoU (changed class)  : {iou:.4f}")
    print(f"F1 (changed class)   : {f1:.4f}")
    print(f"Precision            : {precision:.4f}")
    print(f"Recall                : {recall:.4f}")
    print(f"Pixel accuracy        : {pixel_acc:.4f}")
    print(f"Confusion (pixel)     : TP={tp:,} FP={fp:,} FN={fn:,} TN={tn:,}")
    print(
        "\nCATATAN: metrik ini di level PIXEL dalam patch 256x256, BUKAN level "
        "polygon/area geografis. Interpretasi hati-hati -- kelas 'berubah' "
        "minoritas (lihat DATASET_MANIFEST.md, class imbalance), jadi IoU/F1 "
        "lebih informatif daripada accuracy (accuracy gampang tinggi semu "
        "kalau model cuma nebak 'tidak berubah' terus)."
    )

    return {
        "iou": iou, "f1": f1, "precision": precision, "recall": recall,
        "pixel_acc": pixel_acc, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--split", type=str, default="test", choices=["train", "val", "test", "jasansky_val", "jasansky_train"])
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--subset-size", type=int, default=None, help="buat uji cepat")
    args = parser.parse_args()
    evaluate(args.checkpoint, args.split, args.batch_size, args.threshold, args.subset_size)
