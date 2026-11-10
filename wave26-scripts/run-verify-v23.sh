#!/bin/bash
# Wave 26 Round 3: run the v23 verification (WSL side; the FD/shim come from the untouched tree).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
FD=~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
SHIM=~/hakios/uefi-udon/BootShim/BootShim.bin

python3 $R/wave26-scripts/verify-udon-hakios-v23.py \
  "$R/device-layer/udon-hakios-grafted-v23.img" \
  "$R/device-layer/stock-boot-a.img" \
  $SHIM $FD \
  "$R/device-layer/udon-hakios-payload-v23.bin" \
  "$R/device-layer/udon-hakios-payload-v22.bin" \
  "$R/wave26-scripts/udon-hakios-cmdline-v23.bin" \
  "$R/device-layer/hakios-kernel-v21.bin"
