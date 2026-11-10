#!/bin/bash
# Wave 18: pull the final logdump partition off the phone (the last boot cycle
# before the ABL fallback to Android) into the repo, with sha256.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
REPO=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
adb wait-for-device
adb root >/dev/null 2>&1; sleep 3
echo "slot: $(adb shell getprop ro.boot.slot_suffix)"
adb shell "su -c 'blockdev --getsize64 /dev/block/by-name/logdump'"
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w18-logdump.bin bs=4096'"
adb pull /data/local/tmp/w18-logdump.bin "$REPO/logdump-v12.bin"
adb shell "su -c 'rm -f /data/local/tmp/w18-logdump.bin'"
sha256sum "$REPO/logdump-v12.bin"
ls -la "$REPO/logdump-v12.bin"
