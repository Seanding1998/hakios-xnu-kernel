#!/bin/bash
# Drive the phone to Android: when the loader serves, stop/reboot it (each reset is one failed
# boot_b attempt for ABL); when its counter runs out, ABL boots slot a (Android).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[loop $(date +%H:%M:%S)] $*"; }
for round in $(seq 1 25); do
  # an Android on the bus ends everything
  if usbipd list 2>/dev/null | grep -q 22d9; then LOG "ANDROID IS ON THE BUS"; exit 0; fi
  RES=$($LT --timeout 10000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ "$RES" = "running" ]; then
    LOG "round $round: session live: oem stop"
    $LT --timeout 10000 cmd "oem stop" 2>/dev/null | grep -q OKAY || true
    sleep 3
  fi
  LOG "round $round: reboot (result was '$RES')"
  $LT --timeout 10000 cmd "reboot" 2>/dev/null | grep -q OKAY && LOG "  reboot accepted" || LOG "  (the loader is not answering right now)"
  sleep 45
done
LOG "25 rounds without Android: give up"
