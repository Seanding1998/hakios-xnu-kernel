#!/bin/bash
# Wave 45 fast path: the user force-reboots and holds vol-up into a FRESH fastboot.
# This catcher polls for a live ABL (getvar answers taro) and immediately hands
# the window to flash-bootb-v36.sh --fb. The wedged gadget answers FAILED/hang,
# never taro - it can never trigger the flash.
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG="$R/wave45-scripts/fastboot-catch-v45.log"
echo "[$(date +%H:%M:%S)] catcher armed: polling for a live ABL fastboot (12 min window)" >> "$LOG"
for i in $(seq 1 90); do
    LINE=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
    if [ -z "$LINE" ]; then sleep 8; continue; fi
    NAME=$(printf '%s' "$LINE" | awk '{print $3}')
    [ "$NAME" = "xnuloader" ] && { sleep 8; continue; }
    BUSID=$(printf '%s' "$LINE" | awk '{print $1}')
    STATE=$(printf '%s' "$LINE" | awk '{print $4}')
    if [ "$STATE" = "Shared" ]; then
        usbipd.exe attach --wsl --busid "$BUSID" >/dev/null 2>&1
        sleep 3
    fi
    OUT=$(wsl -d FedoraLinux-44 --user root -- bash -c 'timeout 6 fastboot getvar product 2>&1' 2>/dev/null | tr -d '\r')
    if printf '%s' "$OUT" | grep -q "product: taro"; then
        echo "[$(date +%H:%M:%S)] LIVE ABL on $BUSID (getvar taro OK) -- launching the direct flash" >> "$LOG"
        bash "$R/wave45-scripts/flash-bootb-v36.sh" --fb "fast$(date +%H%M%S)"
        RC=$?
        echo "[$(date +%H:%M:%S)] flash script exited rc=$RC" >> "$LOG"
        exit $RC
    fi
    sleep 8
done
echo "[$(date +%H:%M:%S)] catcher window expired without a live ABL" >> "$LOG"
exit 1
