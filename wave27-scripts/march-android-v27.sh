#!/bin/bash
# =============================================================================
# Wave 27 -- the Android-state march (zero flash): the phone fell back to
# Android after a sick loader. Pull the logdump evidence, then march it back
# into the slot-b loader cycle so the hunt (running separately) catches the
# fresh generation. Every adb/fastboot call is exit-code checked; getvar
# product=taro is the identity gate; PID-exact kills only. No flash.
# usage: bash march-android-v27.sh <RUNID>
# =============================================================================
set -u
RUNID=${1:?usage: march-android-v27.sh <RUNID>}
LOG() { echo "[march-$RUNID $(date +%H:%M:%S)] $*"; }
DIE() { LOG "STOP: $*"; exit 1; }
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
WFB() { wsl -e bash -lc "sudo -n fastboot $*" 2>&1; }
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037

adb wait-for-device || DIE "adb never saw the device"
BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
[ "$BC" = "1" ] || DIE "android not fully booted ($BC)"

LOG "step 1: logdump evidence"
bash "$R/wave27-scripts/logdump-pull-v27.sh" "$RUNID" || LOG "logdump pull failed (continuing -- the march matters more)"

LOG "step 2: reboot into the ABL fastboot window"
adb reboot bootloader || DIE "adb reboot bootloader failed"
BUSID=""
for i in $(seq 1 90); do
    BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
    [ -n "$BUSID" ] && break
    sleep 2
done
[ -n "$BUSID" ] || DIE "no d00d after the reboot"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
FB=""
for i in $(seq 1 45); do
    W=$(wsl -e bash -lc 'sudo -n fastboot devices 2>/dev/null' 2>/dev/null)
    [ -n "$W" ] && { FB=1; break; }
    sleep 2
done
[ -n "$FB" ] || DIE "fastboot not visible in WSL"

LOG "step 3: identity gate (getvar product must be taro)"
OUT=$(WFB getvar product) || DIE "getvar product failed: $OUT"
printf '%s\n' "$OUT" | grep -qi "product: taro" || DIE "not taro: $OUT"

LOG "step 4: slot gate (must be b)"
CUR=$(WFB getvar current-slot) || DIE "getvar current-slot failed"
CUR=$(printf '%s\n' "$CUR" | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
[ "$CUR" = "b" ] || { WFB set_active b >/dev/null || DIE "set_active b failed"; LOG "set_active b done"; }
LOG "slot: b -- rebooting into the v23 loader cycle"
WFB reboot >/dev/null || DIE "fastboot reboot failed"
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "march complete: the loader cycle is back; the hunt (separately running) takes over"
exit 0
