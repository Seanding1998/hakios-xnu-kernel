#!/bin/bash
# =============================================================================
# Wave 27 -- logdump pull (kernel-side truth of the wedged session), the
# wave16c binary-safe recipe: the WSL Linux adb client over exec-out, size
# gate 201326592, run-id-scoped scratch file. Zero flash.
# usage: bash logdump-pull-v27.sh <RUNID>
# =============================================================================
set -u
RUNID=${1:?usage: logdump-pull-v27.sh <RUNID>}
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
OUT="$R/logdump-v23-wave27-$RUNID.bin"
OUT_WSL="HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/logdump-v23-wave27-$RUNID.bin"
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037

adb wait-for-device || { echo "FATAL: adb never saw the device"; exit 1; }
BC=$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
[ "$BC" = "1" ] || { echo "FATAL: android not fully booted (sys.boot_completed=$BC)"; exit 1; }
adb root >/dev/null 2>&1 || true; sleep 3

echo "[pull-$RUNID] reading logdump (512 MB) via WSL exec-out..."
wsl -e bash -lc "ADB_SERVER_SOCKET=tcp:127.0.0.1:5037 adb exec-out \"su -c 'dd if=/dev/block/by-name/logdump bs=4096 count=131072 2>/dev/null'\" > '$OUT_WSL'" \
    || { echo "FATAL: wsl exec-out dd failed"; exit 1; }
RSIZE=$(stat -c %s "$OUT" 2>/dev/null || echo 0)
[ "$RSIZE" = "536870912" ] || { echo "FATAL: logdump size wrong: $RSIZE (want 536870912)"; exit 1; }
SHA=$(sha256sum "$OUT" | cut -d' ' -f1)
echo "[pull-$RUNID] logdump saved: $OUT ($RSIZE bytes, sha256 $SHA)"
echo "[pull-$RUNID] first keylines:"
grep -aE "loader_return|en0|tcp listen|sshd|feeder|hakios_var_save|memorystatus|ABL|exec" "$OUT" | head -40 || true
exit 0
