#!/bin/bash
# Wait for Android (the ABL fallback), then: bootloader -> flash v15.2 -> boot -> hunt.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LOG() { echo "[auto $(date +%H:%M:%S)] $*"; }

LOG "waiting for Android (22d9 on the bus), up to 40 min"
for i in $(seq 1 80); do
  if usbipd list 2>/dev/null | grep -q 22d9; then LOG "android present (pass $i)"; break; fi
  sleep 30
done
usbipd list 2>/dev/null | grep -q 22d9 || { LOG "no android: give up"; exit 1; }

adb wait-for-device 2>/dev/null || true
sleep 5
LOG "booted state: $(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
LOG "reboot bootloader"
adb reboot bootloader
sleep 20

LOG "waiting for the fastboot gadget in WSL"
G=""
for i in $(seq 1 30); do
  if wsl_out=$(lsusb 2>/dev/null | grep -c d00d); [ "$wsl_out" != "0" ] 2>/dev/null; then G=yes; break; fi
  # usbipd: the persisted binding shares it; attach if needed
  usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  sleep 5
done
[ -n "$G" ] || { LOG "the fastboot gadget never showed"; exit 1; }
LOG "flashing v15.2"
sudo -n fastboot getvar product 2>&1 | head -1
sudo -n fastboot flash boot_b HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v15.img 2>&1 | tail -2
sudo -n fastboot set_active b 2>&1 | tail -1
sudo -n fastboot reboot 2>&1 | tail -1
LOG "flashed; the session auto-runs; hunting"
sleep 30
bash $W/catch-and-run.sh
