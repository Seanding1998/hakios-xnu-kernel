#!/bin/bash
# Wave 42: the full v35 verify (the v34 verify family, re-based on the v35 loader).
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
cd ~/hakios/kernel/xnuloader
python3 "$R/wave42-scripts/verify-udon-hakios-v35.py" \
  "$R/device-layer/udon-hakios-grafted-v35.img" \
  "$R/device-layer/stock-boot-a.img" \
  /home/cyrux/hakios/uefi-udon/BootShim/BootShim.bin \
  /home/cyrux/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  "$R/device-layer/udon-hakios-payload-v35.bin" \
  "$R/device-layer/udon-hakios-payload-v33.bin" \
  "$R/device-layer/udon-hakios-payload-v26.bin" \
  "$R/device-layer/root-apfs-c2780842.bin" \
  | tee "$R/wave42-scripts/verify-v35.log"
