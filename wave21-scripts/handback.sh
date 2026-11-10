#!/bin/bash
# Wait for the ABL fallback to Android, then stabilize: set_active a, so the phone hands back
# to its normal system with slot b keeping the Wave 21 v15.3 image for the next round.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LOG() { echo "[handback $(date +%H:%M:%S)] $*"; }
LOG "waiting for Android (up to 60 min)"
for i in $(seq 1 120); do
  if usbipd list 2>/dev/null | grep -q 22d9; then LOG "android (pass $i)"; break; fi
  sleep 30
done
usbipd list 2>/dev/null | grep -q 22d9 || { LOG "no android"; exit 1; }
timeout 60 adb devices >/dev/null 2>&1
sleep 10
timeout 30 adb reboot bootloader
LOG "bootloader: setting active slot a"
sleep 20
for i in $(seq 1 12); do
  usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  if lsusb 2>/dev/null | grep -q d00d; then break; fi
  sleep 5
done
sudo -n fastboot set_active a 2>&1 | tail -1
sudo -n fastboot reboot 2>&1 | tail -1
LOG "the phone reboots to Android on slot a; slot b keeps v15.3"
