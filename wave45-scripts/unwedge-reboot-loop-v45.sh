#!/bin/bash
# =============================================================================
# Wave 45: unwedge loop for the ABL fastboot gadget that wedged after the
# v36a write failed (05:50:40). The gadget re-enumerates cleanly but drops the
# bulk pair ~1 s after every attach (device-side crash/re-init loop), so no
# fastboot command completes. This loop fires `fastboot reboot` (a single
# short transaction) in every live window: if ONE lands, the phone leaves
# fastboot, boots the active slot, and the slot-b generation cycle resumes --
# the flash watcher then takes the next Android window through the proven
# adb reboot bootloader channel (the wave42 channel).
#
# Nothing here flashes: `fastboot reboot` touches no image. Boot_b stays v35
# (the failed v36a write died in the DOWNLOAD phase, before any partition
# write), boot_a is never touched.
# =============================================================================
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
LOG=$R/wave45-scripts/unwedge-v45.log
END=$(( $(date +%s) + 3900 ))          # run at most 65 minutes
N=0
while [ "$(date +%s)" -lt "$END" ]; do
    N=$((N+1))
    # only while the wedged gadget is on the bus and not already attached elsewhere
    LINE=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
    if printf '%s' "$LINE" | grep -q "Android"; then
        usbipd.exe attach --wsl --busid 2-2 >/dev/null 2>&1
        OUT=$(MSYS_NO_PATHCONV=1 wsl.exe -d FedoraLinux-44 bash -c 'sudo -n timeout 6 fastboot reboot 2>&1' 2>/dev/null | tr -d '\r')
        if printf '%s' "$OUT" | grep -q "OKAY"; then
            echo "[$(date +%H:%M:%S)] try $N: REBOOT OKAY -- the phone is leaving fastboot" >> "$LOG"
            sleep 20
            continue
        fi
        usbipd.exe detach --busid 2-2 >/dev/null 2>&1
        echo "[$(date +%H:%M:%S)] try $N: $(printf '%s' "$OUT" | tail -1 | cut -c1-60)" >> "$LOG"
    else
        echo "[$(date +%H:%M:%S)] try $N: bus has $(printf '%s' "$LINE" | awk '{print $3}' | cut -c1-20) -- recheck" >> "$LOG"
        # retire only if the d00d node is really gone (two checks 10 s apart --
        # a flaky usbipd enumeration must not end the loop early)
        sleep 10
        LINE2=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
        if ! printf '%s' "$LINE2" | grep -q "18d1:d00d"; then
            sleep 10
            LINE3=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
            if ! printf '%s' "$LINE3" | grep -q "18d1:d00d"; then
                echo "[$(date +%H:%M:%S)] the d00d gadget is gone (3 checks); the unwedge loop retires" >> "$LOG"
                break
            fi
        fi
    fi
    sleep 45
done
echo "[$(date +%H:%M:%S)] unwedge loop finished ($N tries)" >> "$LOG"
