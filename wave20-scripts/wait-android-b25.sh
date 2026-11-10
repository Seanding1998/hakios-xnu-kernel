#!/bin/bash
# Wave 20: wait for the boot_b loop to hand back to Android (the v14 session runs
# up to loader_return_after=120 s, then a clean return, then the ABL retry budget
# before the fallback to slot a). Polls every 30 s, hard cap 30 min.
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
START=$(date +%s)
DEADLINE=$((START + 30*60))
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  OUT=$(adb devices 2>/dev/null | grep -c "SERIAL_REDACTED	device")
  if [ "$OUT" -ge 1 ]; then
    echo "android online after $(( $(date +%s) - START )) s"
    adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r'
    adb shell getprop ro.boot.slot_suffix 2>/dev/null | tr -d '\r'
    exit 0
  fi
  sleep 30
done
echo "TIMEOUT waiting for android"
exit 1
