#!/bin/bash
# Wave 23 Round 2 graft (v19b): the v19 graft recipe with the v19b payload. FD (8924cb67)
# and shim (108ce972) are the untouched WSL tree files -- no FD/BootShim rebuild.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=~/hakios/uefi-udon/BootShim/BootShim.bin
STOCK=$R/device-layer/stock-boot-a.img
PAY=$R/device-layer/udon-hakios-payload-v19b.bin
OUT=$R/device-layer/udon-hakios-grafted-v19b.img

echo "-- inputs pinned:"
sha256sum $FD $SHIM $PAY $STOCK
sha256sum $FD | grep -q "^8924cb67" || { echo "FD is not the untouched tree file (8924cb67)"; exit 1; }
sha256sum $SHIM | grep -q "^108ce972" || { echo "shim is not the untouched tree file (108ce972)"; exit 1; }

python3 $R/wave4-scripts/package-udon-boot.py \
  --fd $FD --shim $SHIM --stock $STOCK \
  --payload $PAY \
  --out $OUT \
  --report $OUT.report.json

echo "-- v19b graft:"
sha256sum $OUT
ls -la $OUT $OUT.report.json
