#!/bin/bash
# Watch for the loader gadget in WSL; the moment it appears, one direct probe whose connect
# runs the explicit SET_CONFIGURATION(1) (Wave 21.2's host-side endpoint-wall experiment).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
for i in $(seq 1 200); do
  if lsusb 2>/dev/null | grep -q d00d; then
    echo "[watch $(date +%H:%M:%S)] pass $i: gadget visible, probing"
    timeout 45 sudo -n env LOADER_TALK_NO_GUARD=1 python3 -I "$W/loader_talk.py" --timeout 8000 cmd getvar:result 2>&1 | tail -12
    echo "[watch $(date +%H:%M:%S)] probe done"
  fi
  sleep 3
done
echo "[watch] 200 passes over"
