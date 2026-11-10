#!/bin/bash
# Wave 18: flash v13 (real-init chain) to boot_b via the standard fastboot channel.
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v13.img
echo "local sha256: $(sha256sum "$IMG" | cut -d' ' -f1)"
fastboot getvar product 2>&1 | head -2
fastboot flash boot_b "$IMG"
fastboot set_active b
fastboot reboot
