#!/bin/bash
# Wave 22 graft (v18): the v17b graft recipe with the v18 payload. FD (8924cb67) and shim
# (108ce972) are the untouched WSL tree files -- no FD/BootShim rebuild this round.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=~/hakios/uefi-udon/BootShim/BootShim.bin
STOCK=$R/device-layer/stock-boot-a.img
PAY=$R/device-layer/udon-hakios-payload-v18.bin
OUT=$R/device-layer/udon-hakios-grafted-v18.img

echo "-- inputs pinned:"
sha256sum $FD $SHIM $PAY $STOCK
echo "$FD" | grep -q . && sha256sum $FD | grep -q "^8924cb67" || { echo "FD is not the v17b tree file"; exit 1; }
sha256sum $SHIM | grep -q "^108ce972" || { echo "shim is not the v17b tree file"; exit 1; }
sha256sum $PAY | grep -q "^3f503677" || { echo "payload is not the v18 build"; exit 1; }

python3 ~/hakios/kernel/tools/mkxnuimg.py --help >/dev/null 2>&1 || true
python3 $R/wave4-scripts/package-udon-boot.py \
  --fd $FD --shim $SHIM --stock $STOCK \
  --payload $PAY \
  --out $OUT \
  --report $OUT.report.json

echo "-- v18 graft:"
sha256sum $OUT
ls -la $OUT $OUT.report.json
