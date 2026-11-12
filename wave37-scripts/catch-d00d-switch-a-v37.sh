#!/bin/bash
# =============================================================================
# Wave 37 -- watch for the ABL d00d fastboot gadget after the v27 session ends
# (loader_return_after=600), then switch the active slot to a (set_active only --
# boot_a is NEVER flashed) and reboot into Android so the logdump dd can run.
# Host-side usbipd polling only: no loader knocks, no SSH taps (window discipline).
# usage: bash catch-d00d-switch-a-v37.sh [RUNID]
# =============================================================================
set -u
RUNID=${1:-w37}
LOG() { echo "[catch-$RUNID $(date +%H:%M:%S)] $*"; }
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
WFB() { wsl -e bash -lc "sudo -n fastboot $*" 2>&1; }

LOG "watching for 18d1:d00d (poll 3s, up to 40 min)..."
BUSID=""
for i in $(seq 1 800); do
    LINE=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
    NAME=$(printf '%s' "$LINE" | awk '{print $3}')
    if [ -n "$LINE" ] && [ "$NAME" != "xnuloader" ]; then
        BUSID=$(printf '%s' "$LINE" | awk '{print $1}')
        break
    fi
    sleep 3
done
[ -n "$BUSID" ] || { LOG "STOP: no d00d within 40 min"; exit 1; }
LOG "d00d at $BUSID; attaching"
wsl -e bash -lc 'echo distro up' >/dev/null 2>&1 || true
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
FB=""
for i in $(seq 1 45); do
    W=$(WFB devices 2>/dev/null)
    [ -n "$W" ] && { FB=1; break; }
    sleep 2
done
[ -n "$FB" ] || { LOG "STOP: fastboot not visible in WSL"; usbipd.exe detach --busid "$BUSID" 2>/dev/null || true; exit 1; }

LOG "identity gate (getvar product must be taro)"
OUT=$(WFB getvar product) || { LOG "STOP: getvar failed"; exit 1; }
printf '%s\n' "$OUT" | grep -qi "product: taro" || { LOG "STOP: not taro: $OUT"; exit 1; }
CUR=$(WFB getvar current-slot | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
LOG "current-slot=$CUR; boot_b=v27 already did its generation -> set_active a (flag flip only, boot_a never flashed)"
WFB set_active a >/dev/null || { LOG "STOP: set_active a failed"; exit 1; }
WFB reboot >/dev/null || true
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "rebooted; waiting for Android boot_completed"
adb wait-for-device 2>/dev/null || true
BC=""
for i in $(seq 1 90); do
    BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
    [ "$BC" = "1" ] && break
    sleep 5
done
[ "$BC" = "1" ] || { LOG "STOP: android not fully booted"; exit 1; }
LOG "ANDROID UP (slot a); pulling the logdump"
bash "$R/wave37-scripts/logdump-pull-v37.sh" "$RUNID"
LOG "done"
