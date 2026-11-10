#!/bin/bash
# Wave 20: flash boot_b = v14 via the standard WSL root fastboot channel.
# Prereq: the phone is in bootloader mode and usbipd-attached to WSL.
set -e
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v14.img
LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
echo "local sha256: $LOCAL_SHA"
echo "-- devices:"
fastboot devices
echo "-- getvar product (expect taro):"
fastboot getvar product 2>&1 | head -2
echo "-- getvar current-slot:"
fastboot getvar current-slot 2>&1 | head -2
echo "-- flashing boot_b (192 MiB) ---"
fastboot flash boot_b "$IMG"
fastboot set_active b
echo "-- rebooting into the launchd session (loader_return_after=120) --"
fastboot reboot
