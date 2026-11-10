#!/bin/bash
# Wave 26 Round 2 (the last flash of this wave): flash boot_b = v22 (the maxvnodes loader)
# via the standard WSL root fastboot channel. EXPECT_SHA pins the graft.
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v22.img
EXPECT_SHA=WAVE26_SET_ME
LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "local sha256: $LOCAL_SHA"
if [ "$EXPECT_SHA" = "WAVE26_SET_ME" ]; then
  echo "EXPECT_SHA not pinned yet -- recording it into this script now:"
  sed -i "s/^EXPECT_SHA=WAVE26_SET_ME/EXPECT_SHA=$LOCAL_SHA/" "$0"
  echo "pinned EXPECT_SHA=$LOCAL_SHA (re-run to flash)"
  exit 0
fi
[ "$LOCAL_SHA" = "$EXPECT_SHA" ] || { echo "FATAL: graft sha mismatch"; exit 1; }
echo "-- devices:"
sudo -n fastboot devices
echo "-- getvar product (expect taro):"
timeout 15 sudo -n fastboot getvar product 2>&1 | head -2
echo "-- flashing boot_b (192 MiB) with v22 ---"
sudo -n fastboot flash boot_b "$IMG" 2>&1 | tail -3
sudo -n fastboot set_active b
echo "-- rebooting into the Wave 26 v22 session (the maxvnodes loader) --"
sudo -n fastboot reboot
