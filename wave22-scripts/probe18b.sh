#!/bin/bash
# Wave 22 probe 2: like probe18 but with the guardian OFF (the round-1 surgery race killed
# the shot) and three attempts spread across the window. The stderr it captures shows
# libusb's set_configuration(1) answer -- the T2 verdict from the host's side.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
OUT=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave22-scripts/probe18b.log
LOG() { echo "[probe18b $(date +%H:%M:%S)] $*" >> $OUT; }

LOG "=== armed (guardian off); waiting for a d00d window ==="
for i in $(seq 1 900); do
  LINE=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$LINE" | grep -q "18d1:d00d" && echo "$LINE" | grep -qE "Shared|Attached"; then
    LOG "window: $LINE"
    usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q Attached || {
      usbipd attach --wsl --busid 2-2 2>&1 | tail -1 >> $OUT
      sleep 2
    }
    for a in 1 2 3; do
      LOG "--- attempt $a ---"
      LOADER_TALK_NO_GUARD=1 timeout 45 sudo -n python3 -I $W/loader_talk.py --timeout 12000 cmd getvar:result >> $OUT 2>&1
      LOG "(attempt $a done)"
      sleep 2
    done
    LOG "=== end ==="
    exit 0
  fi
  sleep 2
done
LOG "no window in 30 min"
