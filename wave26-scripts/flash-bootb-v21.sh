#!/bin/bash
# Wave 26 Round 1: flash boot_b = v21 (the K1 feeder build) via the standard WSL root
# fastboot channel. Run from the fastboot phase (usbipd-attached, phone in bootloader).
# EXPECT_SHA pins the graft; update it from the graft step's output before flashing.
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v21.img
EXPECT_SHA=WAVE26_SET_ME
LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "local sha256: $LOCAL_SHA"
if [ "$EXPECT_SHA" = "WAVE26_SET_ME" ]; then
  echo "EXPECT_SHA not pinned yet -- recording it into this script now:"
  sed -i "s/^EXPECT_SHA=WAVE26_SET_ME/EXPECT_SHA=$LOCAL_SHA/" "$0"
  echo "pinned EXPECT_SHA=$LOCAL_SHA (re-run to flash)"
fi
[ "$(sha256sum "$IMG" | cut -d' ' -f1)" = "$(grep '^EXPECT_SHA=' "$0" | cut -d= -f2)" ] || { echo "FATAL: graft sha mismatch"; exit 1; }
echo "-- devices:"
sudo -n fastboot devices
echo "-- getvar product (expect taro):"
timeout 15 sudo -n fastboot getvar product 2>&1 | head -2
echo "-- flashing boot_b (192 MiB) ---"
sudo -n fastboot flash boot_b "$IMG"
sudo -n fastboot set_active b
echo "-- rebooting into the Wave 26 session (v21: the K1 feeder build) --"
sudo -n fastboot reboot
