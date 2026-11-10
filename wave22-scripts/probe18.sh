#!/bin/bash
# Wave 22: one-shot reactive probe. Poll the bus at 2 s; the moment the loader's gadget is
# visible and shared (18d1:d00d), attach it to WSL and run ONE loader_talk probe with the
# guardian ON and stderr VISIBLE -- the set_configuration(1) answer is the T2 verdict the
# catch loop has been discarding. Fires once, then exits.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave22-scripts
OUT=$W/probe18.log
LOG() { echo "[probe18 $(date +%H:%M:%S)] $*" >> $OUT; }

LOG "=== armed; waiting for the next 18d1:d00d window ==="
for i in $(seq 1 400); do
  LINE=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$LINE" | grep -q "18d1:d00d" && echo "$LINE" | grep -qE "Shared|Attached"; then
    LOG "window: $LINE"
    break
  fi
  sleep 2
done
usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q Attached || {
  LOG "attaching"
  usbipd attach --wsl --busid 2-2 2>&1 | tail -1 >> $OUT
  sleep 3
}
LOG "=== probing (stderr visible) ==="
timeout 60 sudo -n python3 -I HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts/loader_talk.py --timeout 15000 cmd getvar:result >> $OUT 2>&1
LOG "=== probe done; second look ==="
timeout 60 sudo -n python3 -I HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts/loader_talk.py --timeout 15000 cmd getvar:result >> $OUT 2>&1
LOG "=== end ==="
