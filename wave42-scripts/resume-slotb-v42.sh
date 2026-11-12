#!/bin/bash
# =============================================================================
# Wave 42: resume the v35 slot-b cycle after the device fell back to Android
# (the wave38 generation-loop interruption, seen live again). boot_a is NEVER
# flashed -- this script only ever does a SLOT SWITCH back to b, the operation
# the red lines authorize. Gates kept: the gadget must be the ABL fastboot
# (product=taro, name != xnuloader); current-slot is RECORDED before the switch
# (field evidence); set_active b asserted; reboot.
# usage: bash resume-slotb-v42.sh [RUNID]
# =============================================================================
set -u
RUNID=${1:-$(date +%H%M%S)}
LOG() { echo "[resume-$RUNID $(date +%H:%M:%S)] $*"; }
DIE() { LOG "STOP: $*"; exit 1; }
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
WFB() { wsl -e bash -lc "sudo -n fastboot $*" 2>&1; }

LOG "waiting for the Android state (22d9:2765/2769)..."
SEEN=""
for i in $(seq 1 120); do
    ST=$(usbipd.exe list 2>/dev/null | grep -cE "22d9:276[59]" || true)
    if [ "$ST" -ge 1 ]; then SEEN=1; break; fi
    sleep 5
done
[ -n "$SEEN" ] || DIE "no Android within 10 min"
adb wait-for-device 2>/dev/null || true
BC=""
for i in $(seq 1 60); do
    BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
    [ "$BC" = "1" ] && break
    sleep 5
done
[ "$BC" = "1" ] || DIE "android not fully booted"
LOG "adb reboot bootloader"
adb reboot bootloader || DIE "adb reboot bootloader failed"

LOG "waiting for the ABL fastboot gadget"
BUSID=""
for i in $(seq 1 120); do
    LINE=$(usbipd.exe list 2>/dev/null | grep "18d1:d00d" | head -1)
    NAME=$(printf '%s' "$LINE" | awk '{print $3}')
    if [ -n "$LINE" ] && [ "$NAME" != "xnuloader" ]; then
        BUSID=$(printf '%s' "$LINE" | awk '{print $1}')
        break
    fi
    sleep 2
done
[ -n "$BUSID" ] || DIE "no ABL fastboot gadget"

wsl -e bash -lc 'echo distro up' >/dev/null 2>&1 || DIE "distro does not start"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
FB=""
for i in $(seq 1 45); do
    W=$(wsl -e bash -lc 'sudo -n fastboot devices 2>/dev/null' 2>/dev/null)
    [ -n "$W" ] && { FB=1; break; }
    sleep 2
done
[ -n "$FB" ] || { LOG "fastboot not visible; detach"; usbipd.exe detach --busid "$BUSID" 2>/dev/null || true; exit 1; }

OUT=$(WFB getvar product) || DIE "getvar product failed: $OUT"
printf '%s\n' "$OUT" | grep -qi "product: taro" || DIE "not taro: $OUT"

CUR=$(WFB getvar current-slot) || DIE "getvar current-slot failed"
CUR=$(printf '%s\n' "$CUR" | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
LOG "FIELD EVIDENCE: current-slot at resume = $CUR (the fall-to-Android flipped the active slot off b)"
[ "$CUR" = "b" ] || { WFB set_active b >/dev/null || DIE "set_active b failed"; LOG "set_active b done"; }
CUR2=$(WFB getvar current-slot) || DIE "getvar current-slot (post) failed"
CUR2=$(printf '%s\n' "$CUR2" | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
[ "$CUR2" = "b" ] || DIE "slot did not take (still $CUR2)"

LOG "rebooting into the slot-b cycle"
WFB reboot >/dev/null || LOG "fastboot reboot failed"
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "RESUME DONE: the v35 loader cycle restarts ($(date +%H:%M:%S))"
