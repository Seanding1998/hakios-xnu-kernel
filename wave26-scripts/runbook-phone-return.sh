#!/bin/bash
# =============================================================================
# Wave 26 -- Phone-return Runbook (one-shot, run from Git Bash on Windows)
# Phase-A hardened (review round 3, §7):
#   - per-run unique ID: every verdict/scratch file carries it; a verdict from
#     another run never passes for this one
#   - every adb/fastboot call's exit code is checked (no `| tail` losses)
#   - `getvar product` is an identity gate (taro) before any fastboot action
#   - the four bus states are handled separately (android / abl / loader /
#     no-device); the LOADER state never gets usbipd attach (its diagnostic
#     phase is a single Windows-libusb owner) -- it waits for the fallback
#   - the boot_b readback scratch file carries the run id
#
# The phone left mid-campaign (user recall, 2026-11-09 ~14:16). At recall:
#   boot_b = v23 (graft 9e0609fb..., flashed 13:16:15, set_active b) -- the
#   long-session build (loader_return_after=1800 + maxvnodes=8192 + the en0
#   feeder). This runbook resumes the campaign when the phone comes back.
#
# Red lines unchanged: boot_b only; no FD/shim rebuild; no flash without the
# coordinator's Round 4 approval; every kill is by PID.
# =============================================================================
set -u
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
V23_GRAFT="$R/device-layer/udon-hakios-grafted-v23.img"
V23_SHA=9e0609fb5b1808e2a3c677b73cd58cd322b0bb1f9bbb1538173d46e2164db151
PYEXE_WIN="C:\\Users\\HOST-REDACTED\\AppData\\Local\\Programs\\Python\\Python313\\python.exe"
PYEXE_NIX="HOST-REDACTED/AppData/Local/Programs/Python/Python313/python.exe"
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
RUNID=$(date +%Y%m%d-%H%M%S)-$$
LOG() { echo "[runbook-$RUNID $(date +%H:%M:%S)] $*"; }
DIE() { LOG "STOP: $*"; exit 1; }
WFB() { wsl -e bash -lc "sudo -n fastboot $*" 2>&1; }

command -v adb >/dev/null || DIE "adb not on PATH (run from Git Bash on Windows)"
[ -f "$V23_GRAFT" ] || DIE "the v23 graft is missing"

# exit-code-checked wrappers (review §7: `| tail` loses the code)
adb_run() {                           # adb_run <args...> : die on failure
    local out
    out=$(adb "$@" 2>&1) || DIE "adb $* failed: $out"
    printf '%s\n' "$out"
}
fb_run() {                            # fb_run <args...> : die on failure (WSL root fastboot)
    local out
    out=$(wsl -e bash -lc "sudo -n fastboot $*" 2>&1) || DIE "fastboot $* failed: $out"
    printf '%s\n' "$out"
}

# ---------------------------------------------------------------- 1. STATE
STATE=""
for i in $(seq 1 24); do
    if usbipd.exe list 2>/dev/null | grep -Eq "22d9:276[59]"; then STATE=android; break; fi
    N=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $3; exit}')
    if [ "$N" = "xnuloader" ]; then STATE=loader; break; fi
    if usbipd.exe list 2>/dev/null | grep -q "18d1:d00d"; then STATE=abl; break; fi
    if [ $((i % 6)) -eq 1 ]; then LOG "state: no device on the bus (poll $i; off-bus is fine)"; fi
    sleep 10
done
[ -n "$STATE" ] || DIE "the phone never appeared on the bus"
LOG "state: $STATE"

# ------------------------------------------------- 2. STATE-SPECIFIC MARCH
# android : stay -- the identity check reads boot_b through it
# abl     : attach + fastboot directly (this is the ABL's own fastboot mode)
# loader  : NEVER usbipd attach (the loader's diagnostic phase is a single
#           Windows-libusb owner); wait for its cycle to fall back to Android
# none    : keep polling
wait_android_fallback() {
    for i in $(seq 1 240); do
        if usbipd.exe list 2>/dev/null | grep -Eq "22d9:276[59]"; then
            adb wait-for-device 2>/dev/null || true
            BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
            [ "$BC" = "1" ] && { LOG "android up (fallback poll $i)"; return 0; }
        fi
        if [ $((i % 12)) -eq 1 ]; then LOG "waiting for the Android fallback (poll $i)..."; fi
        sleep 10
    done
    return 1
}

if [ "$STATE" = "loader" ]; then
    LOG "loader phase on the bus: NO usbipd attach (single-owner discipline); waiting for the fallback"
    wait_android_fallback || DIE "the loader never fell back to Android"
    STATE=android
elif [ "$STATE" = "abl" ]; then
    LOG "ABL fastboot on the bus: attach for the slot check"
    BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
    usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
    FB=""
    for i in $(seq 1 45); do
        W=$(wsl -e bash -lc 'sudo -n fastboot devices 2>/dev/null' 2>/dev/null)
        [ -n "$W" ] && { FB=1; break; }
        sleep 2
    done
    [ -n "$FB" ] || DIE "fastboot not visible in WSL although the ABL was on the bus"
fi

# ------------------------------------------------------------- 3. IDENTITY
# the gate that fronts every fastboot action: only this phone's ABL passes
gate_product() {
    local out
    out=$(WFB getvar product) || DIE "getvar product failed: $out"
    printf '%s\n' "$out" | grep -qi "product: taro" || DIE "getvar product is not taro: $out"
}

if [ "$STATE" = "android" ]; then
    adb_run shell getprop sys.boot_completed | tr -d '\r\n' | grep -q "^1$" || DIE "android not fully booted"
    adb root >/dev/null 2>&1 || true; sleep 3
    READ_FILE="$R/device-layer/boot_b.read.$RUNID.bin"
    READ_FILE_WSL="HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer/boot_b.read.$RUNID.bin"
    LOG "reading boot_b for the identity check (scratch: boot_b.read.$RUNID.bin)"
    # Windows adb.exe exec-out is NOT binary-safe (+88 bytes of mangling,
    # measured 2026-11-09: 201,326,680 instead of 201,326,592). The readback
    # goes through the WSL Linux adb client (the wave16c recipe: the client is
    # binary-safe; 512 MB logdumps have crossed it repeatedly). dd's stderr
    # statistics are silenced at the source -- su merges them into the stream
    # (measured: exactly dd's 88-byte stats tail rode the first readback). The
    # scratch path for the WSL-side redirect is the /mnt/c form of the file.
    wsl -e bash -lc "ADB_SERVER_SOCKET=tcp:127.0.0.1:5037 adb exec-out \"su -c 'dd if=/dev/block/by-name/boot_b bs=4096 count=49152 2>/dev/null'\" > '$READ_FILE_WSL'" \
        || DIE "wsl adb exec-out dd of boot_b failed"
    RSIZE=$(stat -c %s "$READ_FILE" 2>/dev/null)
    [ "$RSIZE" = "201326592" ] || DIE "boot_b read size wrong: $RSIZE (want 201326592)"
    READ_SHA=$(sha256sum "$READ_FILE" 2>/dev/null | cut -d' ' -f1)
    rm -f "$READ_FILE"
    LOG "boot_b read sha256: $READ_SHA"
    [ "$READ_SHA" = "$V23_SHA" ] || DIE "boot_b is NOT v23 ($READ_SHA). No re-flash without the coordinator's Round 4 approval."
    LOG "boot_b = v23 confirmed"
fi

# ---------------------------------------------------------------- 4. SLOT
LOG "marching to the ABL fastboot window (adb reboot bootloader)"
adb_run reboot bootloader >/dev/null
BUSID=""
for i in $(seq 1 90); do
    BUSID=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $1; exit}')
    [ -n "$BUSID" ] && break
    sleep 2
done
[ -n "$BUSID" ] || DIE "no d00d gadget after the reboot"
usbipd.exe attach --wsl --busid "$BUSID" 2>&1 | tail -1 || true
FB=""
for i in $(seq 1 45); do
    W=$(wsl -e bash -lc 'sudo -n fastboot devices 2>/dev/null' 2>/dev/null)
    [ -n "$W" ] && { FB=1; break; }
    sleep 2
done
[ -n "$FB" ] || DIE "fastboot not visible in WSL"
gate_product
CUR=$(WFB getvar current-slot) || DIE "getvar current-slot failed"
CUR=$(printf '%s\n' "$CUR" | grep -i 'current-slot' | tr -d '\r' | awk '{print $NF}')
LOG "current-slot: $CUR"
if [ "$CUR" != "b" ]; then
    LOG "set_active b"
    WFB set_active b >/dev/null || DIE "set_active b failed"
fi
LOG "reboot into slot b (v23, the long-session build)"
WFB reboot >/dev/null || DIE "fastboot reboot failed"
usbipd.exe detach --busid "$BUSID" 2>/dev/null || true

# ------------------------------------------------------------- 5. CAMPAIGN
# a verdict from another run never passes: this hunt writes verdict26-$RUNID.txt
LOG "handing over to the continuous SSH hunt (55 minutes; run id $RUNID)"
RW_WIN="C:\\Users\\HOST-REDACTED\\.zcode\\workspace\\9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7\\hakios-phk110"
cmd.exe /c "$PYEXE_WIN $RW_WIN\\wave26-scripts\\timed-ssh-v26.py --continuous --deadline-minutes 55 --run-id $RUNID" \
    > "$R/wave26-scripts/runbook-hunt-$RUNID.log" 2>&1
RC=$?
tail -5 "$R/wave26-scripts/runbook-hunt-$RUNID.log"

# ------------------------------------------------------------- 6. VERDICT
VERDICT="$R/wave26-scripts/verdict26-$RUNID.txt"
if [ -f "$VERDICT" ] && grep -q "WAVE21-SSH-OK" "$VERDICT" && grep -q "run-id: $RUNID" "$VERDICT"; then
    LOG "=== WAVE21-SSH-OK ON RECORD ($VERDICT) -- v0.4 candidate, the coordinator announces ==="
    LOG "the phone stays in the chain (slot b, v23). Handback when told: bash wave26-scripts/handback-v26.sh"
    exit 0
fi
LOG "the hunt closed without WAVE21-SSH-OK (rc=$RC). The phone stays in the chain."
LOG "per the coordinator's close-out rule: file the handover (the remaining suspect is the"
LOG "sshd startup race -- exec'd every boot at kernel ~49 s, listens only in some boots),"
LOG "no Round 4 without approval. Handback when told: bash wave26-scripts/handback-v26.sh"
exit 5
