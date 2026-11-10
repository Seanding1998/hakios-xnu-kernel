#!/bin/bash
# Wave 23 Round 2: flash boot_b = v19b via the standard WSL root fastboot channel.
# EXPECT_SHA pins the graft: 5468b6f2fc42608293aaede1f4bf82a276a6784fa0468f62077c72e024676fb8
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v19b.img
EXPECT_SHA=5468b6f2fc42608293aaede1f4bf82a276a6784fa0468f62077c72e024676fb8
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
echo "-- rebooting into the Wave 23 Round 2 session (v19b: softened re-throw + serve-early + raw code + settle 5s) --"
sudo -n fastboot reboot
