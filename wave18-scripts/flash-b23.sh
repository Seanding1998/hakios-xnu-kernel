#!/bin/bash
# Wave 18 flash: standard channel (WSL root fastboot over usbipd).
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v12.img
LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "local sha256: $LOCAL_SHA"
which fastboot
fastboot getvar product 2>&1 | head -3
fastboot getvar current-slot 2>&1 | head -3
echo "--- flashing boot_b ---"
fastboot flash boot_b "$IMG"
fastboot set_active b
echo "--- rebooting into the loop ---"
fastboot reboot
