#!/bin/bash
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
for i in $(seq 1 24); do
  R=$($LT --timeout 10000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  D=$(lsusb 2>/dev/null | grep -c d00d)
  echo "[p$i $(date +%H:%M:%S)] device=$D result=${R:--}"
  if [ -n "$R" ]; then exit 0; fi
  if [ "$D" = "0" ] && usbipd list 2>/dev/null | grep -q "2-2"; then
    usbipd detach --busid 2-2 >/dev/null 2>&1; sleep 3
    usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  fi
  sleep 20
done
