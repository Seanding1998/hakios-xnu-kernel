#!/bin/bash
# v2: the loader's serving windows are in-session; the wedge after a session ends lifts when a
# full USB re-enumeration lands (usbipd detach+attach). One ABL attempt per cycle:
#   revive -> wait for the session -> oem stop -> reboot -> (phone boots, auto-runs, repeat).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[v2 $(date +%H:%M:%S)] $*"; }

revive() {  # detach/attach until getvar answers; echo the result state or ""
  for t in 1 2 3 4 5 6; do
    R=$($LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
    [ -n "$R" ] && { echo "$R"; return 0; }
    LOG "revive $t: usbipd detach"
    usbipd detach --busid 2-2 >/dev/null 2>&1
    sleep 3
    usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
    sleep 8
  done
  echo ""
}

for round in $(seq 1 20); do
  if usbipd list 2>/dev/null | grep -q 22d9; then LOG "ANDROID IS ON THE BUS"; exit 0; fi
  RES=$(revive)
  if [ -z "$RES" ]; then LOG "round $round: the loader would not revive"; sleep 20; continue; fi
  LOG "round $round: loader alive, result=$RES"
  if [ "$RES" = "running" ]; then
    LOG "  oem stop"
    $LT --timeout 10000 cmd "oem stop" 2>/dev/null | grep -q OKAY || LOG "  (stop unanswered)"
    sleep 2
  fi
  LOG "  reboot"
  $LT --timeout 10000 cmd "reboot" 2>/dev/null | grep -q OKAY && LOG "  accepted" || LOG "  (reboot unanswered)"
  LOG "  waiting 60 s for the next boot"
  sleep 60
done
LOG "20 rounds: give up"
