#!/bin/bash
# =============================================================================
# Wave 28 -- /var persistence gate Runbook (one-shot, run from Git Bash on
# Windows). Encodes "any phone state -> SSH session -> /var verdict":
#
#   subcmd state    : print the observed bus state (android / loader / abl /
#                      none) -- the only device-touching step is metadata-only
#   subcmd march    : Android state -> zero-flash return to the slot-b loader
#                      cycle (delegates to wave27's march-android-v27.sh)
#   subcmd write    : phase-aware watcher until a live session, then the /var
#                      marker WRITE package (delegates to hunt-var-v28.py)
#   subcmd read     : same watcher, then the marker READ package (session 2)
#   subcmd verdict  : compare the write vs read packages -> verdict28-var.txt
#
# Red lines inherited: zero flash (fastboot only getvar/set_active/reboot via
# the march script); the loader phase never gets usbipd attach (single
# Windows-libusb owner -- this runbook owns the device only while its watcher
# child runs); every kill is by PID inside the delegated python tools.
#
# usage: bash runbook-var-gate.sh <state|march|write|read|verdict> [RUNID]
# =============================================================================
set -u
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
PY="HOST-REDACTED\AppData\Local\Programs\Python\Python313\python.exe"
PYX="HOST-REDACTED/AppData/Local/Programs/Python/Python313/python.exe"
export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
SUB=${1:?usage: runbook-var-gate.sh <state|march|write|read|verdict> [RUNID]}
RUNID=${2:-$(date +%Y%m%d-%H%M%S)}
W28="$R/wave28-scripts"
LOG() { echo "[runbook-var-$RUNID $(date +%H:%M:%S)] $*"; }
DIE() { LOG "STOP: $*"; exit 1; }

do_state() {
    if usbipd.exe list 2>/dev/null | grep -Eq "22d9:276[59]"; then
        echo "android"; return 0
    fi
    N=$(usbipd.exe list 2>/dev/null | awk '/18d1:d00d/ {print $3; exit}')
    if [ "$N" = "xnuloader" ]; then echo "loader"; return 0; fi
    if usbipd.exe list 2>/dev/null | grep -q "18d1:d00d"; then echo "abl"; return 0; fi
    echo "none"
}

do_march() {
    [ "$(do_state)" = "android" ] || DIE "march needs the android state (observed: $(do_state))"
    bash "$R/wave27-scripts/march-android-v27.sh" "$RUNID" || DIE "march failed"
    LOG "march done -- the slot-b cycle is running again"
}

do_watch() {   # do_watch <write|read> <tag>
    local MODE=$1 TAG=$2
    LOG "watcher ($MODE, tag $TAG) starting -- single owner until it returns"
    "$PYX" -I "$W28/hunt-var-v28.py" --marker-mode "$MODE" --tag "$TAG" \
        --run-id "$RUNID" --deadline-minutes 200 \
        > "$W28/runbook-$RUNID-$MODE-console.log" 2>&1
    local RC=$?
    [ $RC -eq 0 ] || DIE "watcher ($MODE) failed rc=$RC -- see $W28/hunt-var-v28-$RUNID.log"
    LOG "watcher ($MODE) complete"
}

do_verdict() {   # do_verdict <WRITE_RUN> <READ_RUN>
    local WRUN=${1:?usage: runbook-var-gate.sh verdict <WRITE_RUN> <READ_RUN>}
    local RRUN=${2:?usage: runbook-var-gate.sh verdict <WRITE_RUN> <READ_RUN>}
    "$PYX" -I "$W28/verdict-var-v28.py" --write-run "$WRUN" --read-run "$RRUN" \
        || DIE "verdict failed (see the four-row table above)"
}

case "$SUB" in
    state)   echo "state: $(do_state)" ;;
    march)   do_march ;;
    write)   do_watch write S1 ;;
    read)    do_watch read S2 ;;
    verdict) do_verdict "${2:?}" "${3:?}" ;;
    *)       DIE "unknown subcommand $SUB" ;;
esac
