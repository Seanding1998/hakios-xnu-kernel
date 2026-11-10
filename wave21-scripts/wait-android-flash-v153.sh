#!/bin/bash
# Wait for the ABL fallback to Android, then flash v15.3 (d117e48c) and boot it.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LOG() { echo "[v153 $(date +%H:%M:%S)] $*"; }
LOG "waiting for Android"
for i in $(seq 1 100); do
  if usbipd list 2>/dev/null | grep -q 22d9; then LOG "android (pass $i)"; break; fi
  sleep 30
done
usbipd list 2>/dev/null | grep -q 22d9 || { LOG "no android after 50 min"; exit 1; }
timeout 60 adb devices >/dev/null 2>&1
LOG "reboot bootloader"
timeout 30 adb reboot bootloader
sleep 20
for i in $(seq 1 24); do
  timeout 10 adb attach-wait 2>/dev/null
  usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  if wsl_d00d=$(lsusb 2>/dev/null | grep -c d00d) && [ "$wsl_d00d" != "0" ]; then LOG "gadget in WSL (pass $i)"; break; fi
  sleep 5
done
LOG "flashing v15.3"
sudo -n fastboot flash boot_b $W/../device-layer/udon-hakios-grafted-v15.img 2>&1 | tail -2
sudo -n fastboot set_active b 2>&1 | tail -1
sudo -n fastboot reboot 2>&1 | tail -1
LOG "flashed and rebooted"
