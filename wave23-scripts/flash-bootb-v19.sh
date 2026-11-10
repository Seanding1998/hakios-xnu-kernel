#!/bin/bash
# Wave 23: flash boot_b = v19 via the standard WSL root fastboot channel.
# The phone arrives here in bootloader mode (adb reboot bootloader sent from the Windows
# side; this script talks to the 18d1:d00d gadget through usbipd + WSL fastboot).
# EXPECT_SHA pins the graft: 935360deed1b379b351086efa0fe791a21de77778402ed9202166bfc7bde2aa1
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v19.img
EXPECT_SHA=935360deed1b379b351086efa0fe791a21de77778402ed9202166bfc7bde2aa1
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
echo "-- rebooting into the Wave 23 session (rec_secs=280 rec_ring=1 rec_mb=256, loader_return_after=300) --"
sudo -n fastboot reboot
