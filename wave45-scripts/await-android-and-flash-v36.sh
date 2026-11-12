#!/bin/bash
# Wave 45: wait for the Android window (the ABL fallback ends every slot-b
# generation run; wave42 measured roughly one every 1.5-2 h) and flash boot_b =
# v36 the moment it opens. flash-bootb-v36.sh itself waits up to 20 min for
# Android per call; this wrapper re-arms it until FLASH CONFIRMED.
# Wave 45 addition: once the flash is confirmed, hand the session to the four
# gates runner so the whole pipeline (flash -> gates A-D verdicts) completes
# without another operator.
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
W=$R/wave45-scripts
while true; do
    echo "[$(date +%H:%M:%S)] re-arming the v36 flash (waiting for the Android window)"
    bash "$W/flash-bootb-v36.sh" >> "$W/flash-v36-watch.log" 2>&1
    if grep -q "FLASH CONFIRMED" "$W/flash-v36-watch.log" 2>/dev/null; then
        echo "[$(date +%H:%M:%S)] FLASH CONFIRMED -- handing over to the gates runner"
        sleep 60
        python "$W/gates-run-v45.py" --deadline-minutes 300 --run-id "$(date +%H%M%S)" >> "$W/gates-autorun.log" 2>&1
        echo "[$(date +%H:%M:%S)] the gates runner exited; the watcher retires"
        break
    fi
    echo "[$(date +%H:%M:%S)] flash attempt rc=$? (no window yet); next re-arm in 60 s"
    sleep 60
done
