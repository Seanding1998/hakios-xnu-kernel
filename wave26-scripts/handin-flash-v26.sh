#!/bin/bash
# Wave 26 Round 1: flash boot_b = v21 (the K1 feeder build, graft c18689bc...)
# via the standard channel: Android (slot a) -> adb reboot bootloader -> usbipd
# attach (fastboot phase only) -> WSL root fastboot flash boot_b -> set_active b
# -> reboot -> usbipd detach (the serving phase is a Windows-libusb single owner).
set -e
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
IMG=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v21.img
EXPECT_SHA=c18689bc663f3211dafb5cada870ccf0c17cca9b471ce187d371aaceefbe956f
LOG() { echo "[handin-flash-v26 $(date +%H:%M:%S)] $*"; }

LOCAL_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
LOG "local graft sha256: $LOCAL_SHA"
[ "$LOCAL_SHA" = "$EXPECT_SHA" ] || { LOG "FATAL: graft sha mismatch"; exit 1; }

adb start-server >/dev/null 2>&1 || true
adb wait-for-device
BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
LOG "android online (sys.boot_completed=$BC)"
[ "$BC" = "1" ] || { LOG "android not fully booted; abort"; exit 1; }

LOG "adb reboot bootloader"
adb reboot bootloader

BUSID=""
for i in $(seq 1 90); do
  BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
  [ -n "$BUSID" ] && break
  sleep 2
done
[ -n "$BUSID" ] || { LOG "no d00d gadget on the Windows bus; abort"; exit 1; }
LOG "fastboot gadget at $BUSID; attach --wsl"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -2 || true

FB=""
for i in $(seq 1 45); do
  if sudo -n fastboot devices 2>/dev/null | grep -q .; then FB=1; break; fi
  sleep 2
done
[ -n "$FB" ] || { LOG "fastboot not visible in WSL; abort"; exit 1; }
LOG "getvar: $(timeout 15 sudo -n fastboot getvar product 2>&1 | grep -i '^product' | head -1)"
LOG "getvar current-slot: $(timeout 15 sudo -n fastboot getvar current-slot 2>&1 | grep -i 'current-slot' | head -1)"

LOG "flashing boot_b (192 MiB) with v21 (the K1 feeder build)"
sudo -n fastboot flash boot_b "$IMG" 2>&1 | tail -3
LOG "set_active b"
sudo -n fastboot set_active b
LOG "reboot into slot b (v21 session)"
sudo -n fastboot reboot
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "flash done; boot_b = v21 $LOCAL_SHA; the loader's gadget should enumerate on the Windows bus in ~30 s"
LOG "now start: python wave25-scripts/e2e25.py (reused as-is)"
