#!/bin/bash
# Wave 37 (v27) graft: the v23/v24 graft recipe with the v27 payload (the step-1 probe).
# FD (8924cb67) and shim (108ce972) are the untouched WSL tree files, same as every graft
# since wave 21.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=/home/cyrux/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=/home/cyrux/hakios/uefi-udon/BootShim/BootShim.bin
STOCK=$R/device-layer/stock-boot-a.img
PAY=$R/device-layer/udon-hakios-payload-v27.bin
OUT=$R/device-layer/udon-hakios-grafted-v27.img

echo "-- inputs pinned:"
sha256sum $FD $SHIM $PAY $STOCK
sha256sum $FD | grep -q "^8924cb67" || { echo "FD is not the untouched tree file (8924cb67)"; exit 1; }
sha256sum $SHIM | grep -q "^108ce972" || { echo "shim is not the untouched tree file (108ce972)"; exit 1; }

python3 $R/wave4-scripts/package-udon-boot.py \
  --fd $FD --shim $SHIM --stock $STOCK \
  --payload $PAY \
  --out $OUT \
  --report $OUT.report.json

echo "-- v27 graft:"
sha256sum $OUT
ls -la $OUT $OUT.report.json
