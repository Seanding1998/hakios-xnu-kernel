#!/bin/bash
# Wave 25 evidence + handback: wait for Android to come back (the ABL fallback after
# the loader's cycles, or a manual stop), pull the logdump FRESH (md5 discipline),
# then return the phone to slot a (Android) the standard way.
set -e
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
OUT="$R/logdump-v20-wave25.bin"
LOG() { echo "[ldhb25 $(date +%H:%M:%S)] $*"; }

for i in $(seq 1 240); do
  ST=$(usbipd.exe list 2>/dev/null | grep -c "22d9:2769" || true)
  if [ "$ST" -ge 1 ]; then LOG "android on the bus (poll $i)"; break; fi
  if [ $((i % 6)) -eq 0 ]; then LOG "still cycling (poll $i)"; fi
  sleep 20
done

adb wait-for-device 2>/dev/null || true
sleep 12
LOG "boot_completed: $(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')"
adb root >/dev/null 2>&1 || true; sleep 3
LOG "pulling the logdump partition (fresh evidence of the wave-25 sessions)"
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w25-ld.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w25-ld.bin "$OUT" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w25-ld.bin'" 2>/dev/null || true
LOG "md5: $(md5sum "$OUT" 2>/dev/null | cut -c1-16)  sha256: $(sha256sum "$OUT" 2>/dev/null | cut -c1-16)"

LOG "handback: adb reboot bootloader -> set_active a -> reboot"
adb reboot bootloader
BUSID=""
for i in $(seq 1 90); do
  BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
  [ -n "$BUSID" ] && break
  sleep 2
done
if [ -n "$BUSID" ]; then
  usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
  for i in $(seq 1 45); do
    sudo -n fastboot devices 2>/dev/null | grep -q . && break
    sleep 2
  done
  sudo -n fastboot set_active a
  sudo -n fastboot reboot
  usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
else
  LOG "no fastboot gadget seen; android may already be back"
fi
LOG "handback issued; android should return in ~1 min (22d9:2769 on the bus)"
