#!/bin/bash
# Wave 24: run the v20 verification (WSL side; the FD/shim come from the untouched tree).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=~/hakios/uefi-udon/BootShim/BootShim.bin
KFILE=/tmp/v24/kernel

python3 $R/wave24-scripts/verify-udon-hakios-v20.py \
  "$R/device-layer/udon-hakios-grafted-v20.img" \
  "$R/device-layer/stock-boot-a.img" \
  $SHIM $FD \
  "$R/device-layer/udon-hakios-payload-v24.bin" \
  "$R/device-layer/udon-hakios-payload-v18.bin" \
  "$R/device-layer/udon-hakios-cmdline-v17.bin" \
  $KFILE
