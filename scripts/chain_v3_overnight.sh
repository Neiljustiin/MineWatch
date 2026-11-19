#!/usr/bin/env bash
# Rantai otomatis malam 16-17 Nov 2026 (disetujui Neil):
#   1. tunggu batch download Jasansky selesai
#   2. bikin patch Jasansky ATURAN EKSPANSI, split per-lokasi 75/25 (jasansky_train / jasansky_val held-out)
#   3. v3 = MineNetCD saja + regularisasi penuh (pembanding bersih efek regularisasi)
#   4. v4 = config v3 + jasansky_train (MINEWATCH_INCLUDE_JASANSKY=1)
#   5. eval v2, v3, v4 di 'test' (MineNetCD) dan 'jasansky_val' (held-out Indonesia)
# Log: /tmp/chain_v3.log ; status mesin: /tmp/chain_v3.status (dibaca cron laporan Telegram)
set -u
cd /opt/minewatch/project/scripts
source /opt/minewatch/venv/bin/activate
LOG=/tmp/chain_v3.log; ST=/tmp/chain_v3.status
log(){ echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }
status(){ echo "$*" > "$ST"; }
evalrun(){ # $1=run $2=split [$3=subset]
  local sub=""; [ -n "${3:-}" ] && sub="--subset-size $3"
  log "eval $1 @ $2"
  python3 evaluate.py --checkpoint ../checkpoints/$1/best_model.pt --split $2 $sub 2>&1 | grep -E "^IoU|^F1|^Precision|^Recall|patch\)" | tee -a "$LOG"
}

status "WAIT_DOWNLOAD"
log "chain start; menunggu download Jasansky selesai"
for i in $(seq 1 720); do   # maks 6 jam
  if grep -q "SELESAI" /tmp/jasansky_stac.log 2>/dev/null; then break; fi
  if ! pgrep -f jasansky_stac_download.py >/dev/null; then log "WARN: proses download tidak ada & belum SELESAI -> lanjut dengan yang ada"; break; fi
  sleep 30
done
log "download: $(grep -c '\-> done' /tmp/jasansky_stac.log) done, $(grep -c '\-> excluded' /tmp/jasansky_stac.log) excluded(before sudah tambang, tetap dipakai), $(grep -c '\-> failed\|\-> error' /tmp/jasansky_stac.log) failed"

status "BUILD_PATCHES"
rm -rf ../data/training_datasets/jasansky_patches
if python3 jasansky_build_patches.py --src ../data/sentinel2_jasansky_stac --out ../data/training_datasets/jasansky_patches --val-frac 0.25 >> "$LOG" 2>&1; then
  log "build patches OK: $(python3 -c "import json;s=json.load(open('../data/training_datasets/jasansky_patches/summary.json'));print('train_tiles=',len(s['train_tiles']),'val_tiles=',len(s['val_tiles']),'train_patches=',s['jasansky_train_patches'],'(pos',s['jasansky_train_positive'],') val_patches=',s['jasansky_val_patches'],'(pos',s['jasansky_val_positive'],')')")"
  JAS_OK=1
else
  log "build patches GAGAL (lihat log) -> v3 tetap jalan; v4 dilewati"; JAS_OK=0
fi

status "TRAIN_V3"
log "launch v3 (base_ch=64, epochs=50, MineNetCD saja, regularisasi penuh)"
python3 train_production.py --base-ch 64 --epochs 50 --run-name production_v3_base64_reg > /tmp/production_v3.log 2>&1
RC=$?
log "v3 selesai rc=$RC; $(grep -c '^Epoch' /tmp/production_v3.log) epoch; $(grep 'Selesai' /tmp/production_v3.log | tail -1)"
if [ $RC -ne 0 ]; then status "TRAIN_V3_FAILED"; log "v3 GAGAL"; exit 1; fi

status "EVAL_V3"
evalrun production_v2_base64 test 2000
evalrun production_v3_base64_reg test 2000
if [ "$JAS_OK" = "1" ]; then evalrun production_v2_base64 jasansky_val; evalrun production_v3_base64_reg jasansky_val; fi

if [ "$JAS_OK" = "1" ]; then
  status "TRAIN_V4"
  log "launch v4 (config v3 + jasansky_train, MINEWATCH_INCLUDE_JASANSKY=1)"
  MINEWATCH_INCLUDE_JASANSKY=1 python3 train_production.py --base-ch 64 --epochs 50 --run-name production_v4_base64_reg_jasansky > /tmp/production_v4.log 2>&1
  RC=$?
  log "v4 selesai rc=$RC; $(grep -c '^Epoch' /tmp/production_v4.log) epoch; $(grep 'Selesai' /tmp/production_v4.log | tail -1)"
  if [ $RC -ne 0 ]; then status "TRAIN_V4_FAILED"; log "v4 GAGAL"; exit 1; fi
  status "EVAL_V4"
  evalrun production_v4_base64_reg_jasansky test 2000
  evalrun production_v4_base64_reg_jasansky jasansky_val
fi
status "DONE"
log "chain DONE"
