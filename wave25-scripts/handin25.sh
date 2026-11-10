#!/bin/bash
# Wave 25 hand-in: ZERO-FLASH boot of slot b. boot_b already holds v20 (Boot #38,
# graft 05267a64...); this only re-points the active slot: Android (slot a) ->
# bootloader -> usbipd attach (fastboot only) -> set_active b -> reboot.
# After the reboot the loader's gadget is deliberately left UNATTACHED: the serving
# phase is a Windows-libusb single owner (wave25-scripts/e2e25.py).
set -e
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
LOG() { echo "[handin25 $(date +%H:%M:%S)] $*"; }

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
LOG "set_active b (zero flash: boot_b keeps v20 05267a64...)"
sudo -n fastboot set_active b
LOG "reboot into slot b"
sudo -n fastboot reboot
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "hand-in done; the loader's gadget should enumerate on the Windows bus in ~30 s"
LOG "now start: python wave25-scripts/e2e25.py"
