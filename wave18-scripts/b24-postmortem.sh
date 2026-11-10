#!/bin/bash
# Wave 18 b24 post-mortem: pull the final logdump + hash the HFS+ data volume
# region (blocks 2042368..5242874). Pristine = 88c1cd9986b77d382c0b92bb7a953b14d7be67121ae400ea8dd53e292bc96bd8
# (wave16c). A different hash = the kernel wrote the volume (skeleton/journal)
# through the S3 write path = physical persistence evidence.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
REPO=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
adb wait-for-device
adb root >/dev/null 2>&1; sleep 3
echo "slot: $(adb shell getprop ro.boot.slot_suffix | tr -d '\r')"
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w18ld.bin bs=4096 count=32'" 2>&1 | tail -1
adb pull /data/local/tmp/w18ld.bin "$REPO/logdump-v13.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w18ld.bin'"
sha256sum "$REPO/logdump-v13.bin"
echo "-- data volume full-region sha (pristine 88c1cd99...):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=3200507 2>/dev/null | sha256sum'" | tr -d '\r'
echo "-- volume header block @2042368 (pristine 337114380f94...):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=1 2>/dev/null | sha256sum'" | tr -d '\r'
