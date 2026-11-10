#!/bin/bash
# Wave 26 handback: wait for Android (the ABL fallback), pull the final logdump
# (the last sessions' kernel logs), then set_active a and reboot = the phone
# back to the user on Android.
set -e
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[hb26 $(date +%H:%M:%S)] $*"; }

LOG "waiting for the ABL fallback to Android..."
SEEN=""
for i in $(seq 1 720); do
  ST=$(usbipd.exe list 2>/dev/null | grep -c "22d9:2769" || true)
  if [ "$ST" -ge 1 ]; then SEEN=1; break; fi
  if [ $((i % 30)) -eq 0 ]; then LOG "still cycling (poll $i)"; fi
  sleep 5
done
[ -n "$SEEN" ] || { LOG "no Android within the wait; abort (the phone stays cycling)"; exit 1; }
adb wait-for-device 2>/dev/null || true
for i in $(seq 1 60); do
  BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
  [ "$BC" = "1" ] && break
  sleep 5
done
LOG "android up; pulling the final logdump"
adb root >/dev/null 2>&1 || true; sleep 3
adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w26-ld-final.bin bs=4096'" 2>&1 | tail -1
adb pull /data/local/tmp/w26-ld-final.bin "$R/logdump-v23-wave26-final.bin" 2>&1 | tail -1
adb shell "su -c 'rm -f /data/local/tmp/w26-ld-final.bin'" 2>/dev/null || true
LOG "final logdump md5: $(md5sum "$R/logdump-v23-wave26-final.bin" 2>/dev/null | cut -c1-16)"
LOG "handback: set_active a -> reboot (boot_b keeps v23 9e0609fb for the record)"
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
  timeout 15 sudo -n fastboot set_active a 2>&1 | tail -1
  sudo -n fastboot reboot 2>&1 | tail -1
  usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
fi
LOG "handback done: slot a (Android); boot_b = v23 9e0609fb stays for the record"
