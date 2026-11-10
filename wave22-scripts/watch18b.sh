#!/bin/bash
# Wave 22: the host-visibility observer. Polls the Windows bus line for the phone (2-2)
# every 20 s and logs every distinct state with a timestamp:
#   22d9      -- Android (fallback or the phone at rest)
#   0000:0002 -- a device the host FAILED to enumerate (the v17b disease: descriptor
#                request failed; the dead devnode)
#   18d1:d00d -- a device the host ENUMERATED (ABL's fastboot gadget or our loader's
#                presented gadget -- the loader's turn is distinguishable by its arrival
#                after a quiet gap ~30 s into the loader phase, and by loader_talk serving)
#   (blank)   -- nothing on the bus (between generations / mid-boot)
# The observation runs ~30 min (several boot cycles), then a summary.
OUT=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave22-scripts/bus18-watch.log
LOG() { echo "[watch18 $(date +%H:%M:%S)] $*" >> $OUT; }
LAST=""
LOG "=== wave22 bus watch begins (round 2, slot b re-booted 23:23:44 (no flash)) ==="
for i in $(seq 1 540); do
  LINE=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1 | sed 's/\s\+/ /g')
  STATE=$(echo "$LINE" | grep -oE "22d9:[0-9a-f]{4}|0000:0002|18d1:d00d" | head -1)
  [ -z "$STATE" ] && STATE="(blank)"
  if [ "$STATE" != "$LAST" ]; then
    LOG "bus: $LAST -> $STATE  [$LINE]"
    LAST=$STATE
  fi
  sleep 20
done
LOG "=== watch ends; final state $LAST ==="
echo "--- state histogram ---" >> $OUT
grep "bus:" $OUT | awk '{print $5}' | sort | uniq -c | sort -rn >> $OUT
