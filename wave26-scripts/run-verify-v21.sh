#!/bin/bash
# Wave 26: run the v21 verification (WSL side; the FD/shim come from the untouched tree).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=~/hakios/uefi-udon/BootShim/BootShim.bin

python3 $R/wave26-scripts/verify-udon-hakios-v21.py \
  "$R/device-layer/udon-hakios-grafted-v21.img" \
  "$R/device-layer/stock-boot-a.img" \
  $SHIM $FD \
  "$R/device-layer/udon-hakios-payload-v21.bin" \
  "$R/device-layer/udon-hakios-payload-v24.bin" \
  "$R/device-layer/udon-hakios-cmdline-v17.bin" \
  "$R/device-layer/hakios-kernel-v21.bin"
