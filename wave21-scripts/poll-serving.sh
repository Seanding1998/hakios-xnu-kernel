#!/bin/bash
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
for i in $(seq 1 40); do
  R=$($LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then
    echo "[poll $i $(date +%H:%M:%S)] SERVING result=$R"
    exit 0
  fi
  D=$(lsusb 2>/dev/null | grep -c d00d)
  echo "[poll $i $(date +%H:%M:%S)] quiet (device=$D)"
  if [ "$D" = "0" ]; then
    usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  fi
  sleep 8
done
echo "never served"
