#!/bin/bash
# Wave 26 Round 2: wait for the ABL's fallback to Android, then flash boot_b = v22
# through the stable channel (adb reboot bootloader -> ABL fastboot -> flash ->
# set_active b -> reboot), then detach (the serving phase is a Windows-libusb owner).
set -e
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
IMG="$R/device-layer/udon-hakios-grafted-v22.img"
EXPECT_SHA=7a1e4811f0d8f46763b3765f6217d5318138b41e8f7b0f3ddf40807852d49acb
LOG() { echo "[flash-v22 $(date +%H:%M:%S)] $*"; }

LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
[ "$LOCAL_SHA" = "$EXPECT_SHA" ] || { LOG "FATAL: graft sha mismatch ($LOCAL_SHA)"; exit 1; }
LOG "graft pinned: $LOCAL_SHA"

LOG "waiting for the ABL fallback to Android (22d9:2769)..."
SEEN=""
for i in $(seq 1 720); do
  ST=$(usbipd.exe list 2>/dev/null | grep -c "22d9:2769" || true)
  if [ "$ST" -ge 1 ]; then SEEN=1; break; fi
  if [ $((i % 30)) -eq 0 ]; then LOG "still cycling (poll $i)"; fi
  sleep 5
done
[ -n "$SEEN" ] || { LOG "no Android within the wait; abort"; exit 1; }
LOG "android on the bus; waiting for boot_completed"
adb wait-for-device 2>/dev/null || true
for i in $(seq 1 60); do
  BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$BC" = "1" ] && break
  sleep 5
done
[ "$BC" = "1" ] || { LOG "android not fully booted; abort"; exit 1; }
LOG "android up; grabbing the fresh logdump before the flash (md5 discipline)"
adb root >/dev/null 2>&1 || true; sleep 3
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w26-ld2.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w26-ld2.bin "$R/logdump-v21-wave26-2.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w26-ld2.bin'" 2>/dev/null || true
LOG "logdump-2 md5: $(md5sum "$R/logdump-v21-wave26-2.bin" 2>/dev/null | cut -c1-16)"

LOG "adb reboot bootloader"
adb reboot bootloader
BUSID=""
for i in $(seq 1 90); do
  BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
  [ -n "$BUSID" ] && break
  sleep 2
done
[ -n "$BUSID" ] || { LOG "no d00d gadget; abort"; exit 1; }
LOG "fastboot gadget at $BUSID; attach --wsl"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -2 || true
FB=""
for i in $(seq 1 45); do
  if sudo -n fastboot devices 2>/dev/null | grep -q .; then FB=1; break; fi
  sleep 2
done
[ -n "$FB" ] || { LOG "fastboot not visible in WSL; abort"; exit 1; }
LOG "getvar: $(timeout 15 sudo -n fastboot getvar product 2>&1 | grep -i '^product' | head -1)"
LOG "flashing boot_b (192 MiB) with v22 (the maxvnodes loader)"
sudo -n fastboot flash boot_b "$IMG" 2>&1 | tail -3
LOG "set_active b"
sudo -n fastboot set_active b
LOG "reboot into slot b (v22 session)"
sudo -n fastboot reboot
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "flash done; boot_b = v22 $LOCAL_SHA"
