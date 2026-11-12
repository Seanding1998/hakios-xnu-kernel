#!/bin/bash
# =============================================================================
# Wave 42: flash boot_b = v35 (the v33 kernel 55a8d40f + the wave39 GL=test
# ramdisk c2780842 + the v35 loader 5de055ea; cmdline = the v26/v33 bytes gpu=1).
# The wave37/v34 channel verbatim, with the v35 image and its graft sha; every
# gate kept:
#   gate 1 (sha):  the local graft must match the pinned sha (6558d303...) before
#                  anything touches the phone (the wave34 lesson: same-name
#                  re-packages MUST re-pin EXPECT_SHA -- this script ships with
#                  the v35 graft's real sha);
#   gate 2 (taro): fastboot getvar product must say taro (the ABL gadget, and
#                  its USB name must NOT be xnuloader);
#   gate 3 (slot): current-slot must be b (set_active b otherwise) -- boot_a
#                  is never touched.
# fastboot runs in WSL on the /mnt/c path, exit code checked and OKAY asserted;
# the distro is woken BEFORE usbipd attach; never wsl --shutdown.
#
# usage: bash flash-bootb-v35.sh [--fb] [RUNID]
# =============================================================================
set -u
RUNID=${2:-$(date +%H%M%S)}
FB_MODE=0
[ "${1:-}" = "--fb" ] && FB_MODE=1
LOG() { echo "[flash-v35-$RUNID $(date +%H:%M:%S)] $*"; }
DIE() { LOG "STOP: $*"; exit 1; }
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
IMG_WIN="$R/device-layer/udon-hakios-grafted-v35.img"
IMG_WSL="/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/udon-hakios-grafted-v35.img"
EXPECT_SHA=6558d303ac792e6e0536b0b80deb3efcaa8195abaa4f398254ae869d7705f0a0
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
WFB() { wsl -e bash -lc "sudo -n fastboot $*" 2>&1; }

LOCAL_SHA=$(sha256sum "$IMG_WIN" | cut -d' ' -f1)
[ "$LOCAL_SHA" = "$EXPECT_SHA" ] || DIE "graft sha mismatch ($LOCAL_SHA)"
LOG "graft pinned: $LOCAL_SHA (payload 82add009, kernel 55a8d40f wave37 first-light, loader 5de055ea the wave42 root-fixed v35 build, ramdisk c2780842 the GL=test carrier, verify 69/69)"

if [ "$FB_MODE" -eq 0 ]; then
    LOG "waiting for the Android state (22d9:2765/2769)..."
    SEEN=""
    for i in $(seq 1 240); do
        ST=$(usbipd.exe list 2>/dev/null | grep -cE "22d9:276[59]" || true)
        if [ "$ST" -ge 1 ]; then SEEN=1; break; fi
        if [ $((i % 12)) -eq 0 ]; then LOG "still not android (poll $i)"; fi
        sleep 5
    done
    [ -n "$SEEN" ] || DIE "no Android within 20 min"
    LOG "android on the bus; waiting for boot_completed"
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
fi

LOG "waiting for the d00d ABL fastboot gadget (serial/name must not be xnuloader)"
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

LOG "waking the distro first, then attach --wsl at $BUSID"
wsl -e bash -lc 'echo distro up' >/dev/null 2>&1 || DIE "distro does not start"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -2 || true
FB=""
for i in $(seq 1 45); do
    W=$(wsl -e bash -lc 'sudo -n fastboot devices 2>/dev/null' 2>/dev/null)
    [ -n "$W" ] && { FB=1; break; }
    sleep 2
done
[ -n "$FB" ] || { LOG "fastboot not visible in WSL; detaching"; usbipd.exe detach --busid "$BUSID" 2>/dev/null || true; exit 1; }

LOG "identity gate (getvar product must be taro)"
OUT=$(WFB getvar product) || DIE "getvar product failed: $OUT"
printf '%s\n' "$OUT" | grep -qi "product: taro" || DIE "not taro: $OUT"

LOG "slot gate (must be b)"
CUR=$(WFB getvar current-slot) || DIE "getvar current-slot failed"
CUR=$(printf '%s\n' "$CUR" | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
[ "$CUR" = "b" ] || { WFB set_active b >/dev/null || DIE "set_active b failed"; LOG "set_active b done"; }

LOG "flashing boot_b (192 MiB) with v35 -- exit-checked, OKAY asserted"
FLLOG=/tmp/flash-v35-$RUNID.log
wsl -e bash -lc "sudo -n fastboot flash boot_b '$IMG_WSL'" > "$FLLOG" 2>&1
FRC=$?
tail -3 "$FLLOG"
[ $FRC -eq 0 ] || { LOG "FLASH FAILED rc=$FRC (boot_b untouched; the phone stays as it was)"; usbipd.exe detach --busid "$BUSID" 2>/dev/null || true; exit 1; }
grep -q "OKAY" "$FLLOG" || { LOG "no OKAY in the flash output -- treating as failed"; usbipd.exe detach --busid "$BUSID" 2>/dev/null || true; exit 1; }

LOG "set_active b + reboot into the v35 cycle"
WFB set_active b >/dev/null || LOG "set_active b failed (continuing: the slot gate said b already)"
WFB reboot >/dev/null || LOG "fastboot reboot failed"
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true
LOG "FLASH CONFIRMED: boot_b = v35 $LOCAL_SHA; the slot-b cycle restarts"
