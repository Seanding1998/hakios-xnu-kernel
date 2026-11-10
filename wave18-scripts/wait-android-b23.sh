#!/bin/bash
# Wave 18: wait for the boot_b loop to fall back to Android (ABL retry budget),
# then confirm the slot is back on a and Android is up. Polls every 30 s.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
START=$(date +%s)
DEADLINE=$((START + 30*60))   # hard cap 30 min
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  OUT=$(adb devices 2>/dev/null | grep -c "SERIAL_REDACTED	device")
  if [ "$OUT" -ge 1 ]; then
    echo "android online after $(( $(date +%s) - START )) s"
    adb shell getprop sys.boot_completed 2>/dev/null
    adb shell getprop ro.boot.slot_suffix 2>/dev/null
    exit 0
  fi
  sleep 30
done
echo "TIMEOUT waiting for android"
exit 1
