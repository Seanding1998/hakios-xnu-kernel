#!/bin/bash
# =============================================================================
# Wave 37 -- logdump pull (the v27 probe console: per-access step-1 lines naming the
# hanging register). The wave27 binary-safe recipe verbatim with a wave37 output name:
# the WSL Linux adb client over exec-out, size gate 536870912, run-id-scoped file.
# Zero flash. Run it AFTER the phone has fallen back to Android.
# usage: bash logdump-pull-v37.sh <RUNID>
# =============================================================================
set -u
RUNID=${1:?usage: logdump-pull-v37.sh <RUNID>}
R=/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
OUT="$R/wave37-scripts/logdump-v26-wave37-$RUNID.bin"
OUT_WSL="/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave37-scripts/logdump-v26-wave37-$RUNID.bin"
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037

adb wait-for-device || { echo "FATAL: adb never saw the device"; exit 1; }
BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
[ "$BC" = "1" ] || { echo "FATAL: android not fully booted (sys.boot_completed=$BC)"; exit 1; }
adb root >/dev/null 2>&1 || true; sleep 3

echo "[w37pull-$RUNID] reading logdump (512 MB) via WSL exec-out..."
wsl -e bash -lc "ADB_SERVER_SOCKET=tcp:127.0.0.1:5037 adb exec-out \"su -c 'dd if=/dev/block/by-name/logdump bs=4096 count=131072 2>/dev/null'\" > '$OUT_WSL'" \
    || { echo "FATAL: wsl exec-out dd failed"; exit 1; }
RSIZE=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
[ "$RSIZE" = "536870912" ] || { echo "FATAL: logdump size wrong: $RSIZE (want 536870912)"; exit 1; }
SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
echo "[w37pull-$RUNID] logdump saved: $OUT ($RSIZE bytes, sha256 $SHA)"
echo "[w37pull-$RUNID] the GPU probe lines:"
grep -aE "adreno:" "$OUT" | head -80 || true
exit 0
