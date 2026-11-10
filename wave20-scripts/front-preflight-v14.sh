#!/bin/bash
# Wave 20 front-write preflight: identity chain + post-b24 data-volume baselines.
# The data volume (blocks 2042368..5242874) must stay untouched this wave:
#   full region 6e40eaef... / volume head @2042368 1e4cd367... (wave18 b24 postmortem).
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
adb wait-for-device
adb root >/dev/null 2>&1; sleep 3
echo "slot: $(adb shell getprop ro.boot.slot_suffix | tr -d '\r')"
echo "-- darwin partition size (expect 21474816000):"
adb shell "su -c 'blockdev --getsize64 /dev/block/sda15'" | tr -d '\r'
echo "-- by-name darwin (expect /dev/block/sda15):"
adb shell "su -c 'readlink -f /dev/block/by-name/darwin'" | tr -d '\r'
echo "-- darwin block 0 (expect the v13 system.apfs NXSB page, sha follows):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 count=1 2>/dev/null | sha256sum'" | tr -d '\r'
echo "-- data volume head @2042368 (expect 1e4cd367... from b24):"
adb shell "su -c 'dd if=/dev/block/by-name/darwin bs=4096 skip=2042368 count=1 2>/dev/null | sha256sum'" | tr -d '\r'
echo "-- free space on /data (need >= 2.7 GB for the push):"
adb shell "df -m /data/local/tmp" | tail -1 | tr -d '\r'
