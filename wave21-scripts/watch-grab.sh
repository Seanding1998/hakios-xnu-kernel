#!/bin/bash
# Watch for the gadget to enumerate and grab it into WSL the moment it is stable, then probe.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
for i in $(seq 1 60); do
  L=$(usbipd list 2>/dev/null | grep "18d1:d00d")
  if [ -n "$L" ]; then
    usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
    D=$(lsusb 2>/dev/null | grep -c d00d)
    if [ "$D" != "0" ]; then
      echo "[$i $(date +%H:%M:%S)] gadget in WSL"
      sleep 3
      R=$(cd $W && timeout 30 sudo -n python3 -I loader_talk.py --timeout 15000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
      echo "[$i] probe: ${R:-<no answer>}"
      exit 0
    fi
  fi
  sleep 6
done
echo "60 passes: no stable gadget"
