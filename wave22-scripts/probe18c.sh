#!/bin/bash
# Wave 22 probe 3: the WSL-side replay tracker. At the next live window: attach, then poll
# lsusb every second for 30 s (does the vhci replay ever produce the device?), then ONE
# loader_talk probe with the guardian genuinely off (sudo env carries the variable -- sudo
# strips a plain prefix assignment).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
OUT=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave22-scripts/probe18c.log
LOG() { echo "[probe18c $(date +%H:%M:%S)] $*" >> $OUT; }

LOG "=== armed; waiting for a window ==="
for i in $(seq 1 900); do
  LINE=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$LINE" | grep -q "18d1:d00d" && echo "$LINE" | grep -qE "Shared|Attached"; then
    LOG "window: $LINE"
    usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q Attached || {
      usbipd attach --wsl --busid 2-2 >> $OUT 2>&1
      LOG "attach rc=$?"
    }
    LOG "polling lsusb for 30 s"
    SEEN=""
    for s in $(seq 1 30); do
      D=$(lsusb 2>/dev/null | grep -i "d00d" | head -1)
      if [ -n "$D" ]; then
        LOG "lsusb($s): $D"
        SEEN=1
        break
      fi
      sleep 1
    done
    if [ -z "$SEEN" ]; then
      LOG "lsusb: the device never appeared in WSL within 30 s"
      LS=$(lsusb 2>/dev/null | head -6)
      LOG "lsusb bus contents: $LS"
    fi
    LOG "--- loader_talk (guardian off) ---"
    timeout 45 sudo -n env LOADER_TALK_NO_GUARD=1 python3 -I $W/loader_talk.py --timeout 12000 cmd getvar:result >> $OUT 2>&1
    LOG "(probe rc=$?)"
    LOG "=== end ==="
    exit 0
  fi
  sleep 2
done
LOG "no window in 30 min"
