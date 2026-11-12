#!/bin/bash
# Wave 45: the full v36 verify (the v35 verify family, re-based on the v36
# payload: the frozen loader 5de055ea + the wave43 kernel 5b77b418 + the wave41
# carrier 51a030c3 + fuelgauge=2 on the cmdline).
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
cd ~/hakios/kernel/xnuloader
python3 "$R/wave45-scripts/verify-udon-hakios-v36.py" \
  "$R/device-layer/udon-hakios-grafted-v36.img" \
  "$R/device-layer/stock-boot-a.img" \
  /home/cyrux/hakios/uefi-udon/BootShim/BootShim.bin \
  /home/cyrux/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  "$R/device-layer/udon-hakios-payload-v36.bin" \
  "$R/device-layer/udon-hakios-payload-v35.bin" \
  "$R/device-layer/udon-hakios-payload-v26.bin" \
  /home/cyrux/hakios/kernel/userland/root.apfs \
  | tee "$R/wave45-scripts/verify-v36.log"
