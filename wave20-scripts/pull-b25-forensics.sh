#!/bin/bash
# Wave 20 b25 post-mortem: pull the final logdump partition + the b25 kernel log
# extraction + hash the HFS+ data volume region (S6-S8 regression: the wave18
# post-b24 baselines are full 6e40eaef... / head @2042368 1e4cd367...).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
REPO=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
adb wait-for-device
adb root >/dev/null 2>&1; sleep 3
echo "slot: $(adb shell getprop ro.boot.slot_suffix | tr -d '\r')"
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w20ld.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w20ld.bin "$REPO/logdump-v14.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w20ld.bin'"
sha256sum "$REPO/logdump-v14.bin"
ls -la "$REPO/logdump-v14.bin"
echo "-- data volume full-region sha (b24 baseline 6e40eaef...):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=3200507 2>/dev/null | sha256sum'" | tr -d '\r'
echo "-- volume header block @2042368 (b24 baseline 1e4cd367...):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=1 2>/dev/null | sha256sum'" | tr -d '\r'
