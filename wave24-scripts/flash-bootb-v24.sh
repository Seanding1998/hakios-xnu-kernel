#!/bin/bash
# Wave 24 Round 1: flash boot_b = v20 (the Exp-1 diagnostic build) via the standard WSL
# root fastboot channel.
# EXPECT_SHA pins the graft: 05267a64c85a5a08ed499fa0a51a3686ed0d4ab8c4cd72ff26546783589cfd6a
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v20.img
EXPECT_SHA=05267a64c85a5a08ed499fa0a51a3686ed0d4ab8c4cd72ff26546783589cfd6a
LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "local sha256: $LOCAL_SHA"
[ "$LOCAL_SHA" = "$EXPECT_SHA" ] || { echo "FATAL: graft sha mismatch"; exit 1; }
echo "-- devices:"
sudo -n fastboot devices
echo "-- getvar product (expect taro):"
timeout 15 sudo -n fastboot getvar product 2>&1 | head -2
echo "-- flashing boot_b (192 MiB) ---"
sudo -n fastboot flash boot_b "$IMG"
sudo -n fastboot set_active b
echo "-- rebooting into the Wave 24 diagnostic session (v20: mirror + pump + standing RX + gate + sampler) --"
sudo -n fastboot reboot
