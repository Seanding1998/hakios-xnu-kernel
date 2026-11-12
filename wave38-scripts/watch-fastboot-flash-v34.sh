#!/bin/bash
# Watch for the user-forced ABL fastboot gadget (18d1:d00d, name != xnuloader) and fire
# the three-gate v34 flash immediately (--fb). Zero other device talkers while armed.
set -u
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG() { echo "[watch-v34 $(date +%H:%M:%S)] $*"; }
for i in $(seq 1 360); do
    LINE=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
    NAME=$(printf '%s' "$LINE" | awk '{print $3}')
    if [ -n "$LINE" ] && [ "$NAME" != "xnuloader" ]; then
        LOG "ABL fastboot gadget appeared ($LINE) -- flashing v34 (GL carrier)"
        bash "$R/wave38-scripts/flash-bootb-v34.sh" --fb w38b
        exit $?
    fi
    sleep 3
done
LOG "no fastboot gadget within 18 min; watcher exits"
exit 1
