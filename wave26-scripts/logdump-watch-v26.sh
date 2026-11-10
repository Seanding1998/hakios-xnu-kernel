#!/bin/bash
# Wave 26 logdump watcher (NO handback): whenever Android appears on the bus,
# pull /dev/block/by-name/logdump (the loader writes the finished session's full
# kernel log there on return -- the frozen sessions' evidence), keep slot b.
# One pull per Android appearance (the logdump only changes when a session ends).
set -u
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[ldw26 $(date +%H:%M:%S)] $*"; }
N=0
LAST_MD5=""

while true; do
  ST=$(usbipd.exe list 2>/dev/null | grep -c "22d9:2769" || true)
  if [ "$ST" -ge 1 ]; then
    adb wait-for-device 2>/dev/null || true
    sleep 10
    BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
    if [ "$BC" = "1" ]; then
      N=$((N+1))
      OUT="$R/logdump-v21-wave26-$N.bin"
      LOG "android up (sys.boot_completed=1); pulling logdump #$N"
      adb root >/dev/null 2>&1 || true; sleep 3
      adb shell "su -c 'dd if=/dev/block/by-name/logdump of=/data/local/tmp/w26-ld.bin bs=4096'" 2>&1 | tail -1
      adb pull /data/local/tmp/w26-ld.bin "$OUT" 2>&1 | tail -1
      adb shell "su -c 'rm -f /data/local/tmp/w26-ld.bin'" 2>/dev/null || true
      M=$(md5sum "$OUT" 2>/dev/null | cut -d' ' -f1)
      LOG "logdump #$N md5: ${M:0:16} size: $(stat -c%s "$OUT" 2>/dev/null)"
      if [ "$M" != "$LAST_MD5" ] && [ -n "$M" ]; then
        LAST_MD5="$M"
        grep -c "MiniIOMobileFramebuffer\|created surface\|backboardd\|SpringBoard" "$OUT" 2>/dev/null | head -1 | xargs -I{} echo "[ldw26] display-line count: {}"
      fi
      sleep 60
    fi
  fi
  sleep 20
done
