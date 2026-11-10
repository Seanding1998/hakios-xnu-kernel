#!/bin/bash
# wave27: the reset cycle -- pause hunt, hot reset, watch 90 s for the node
# drop; relaunch the hunt either way (drop = fresh generation ahead).
# Every kill by exact PID. usage: bash reset-cycle-v27.sh
set -u
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
PY="HOST-REDACTED\AppData\Local\Programs\Python\Python313\python.exe"
LOG() { echo "[reset-cycle $(date +%H:%M:%S)] $*"; }
PID=$(powershell -NoProfile -Command 'Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "timed-ssh-v27" } | Select-Object -First 1 -ExpandProperty ProcessId' | tr -d '\r')
if [ -n "$PID" ]; then taskkill //F //T //PID "$PID" >/dev/null 2>&1; LOG "hunt $PID paused"; fi
sleep 2
"$R/wave26-scripts/revive-v26.py" >/dev/null 2>&1   # the hot reset lives there
LOG "reset issued"
DROPPED=no
for i in $(seq 1 6); do
    sleep 15
    if ! usbipd.exe list 2>/dev/null | grep -q "18d1:d00d"; then DROPPED=yes; LOG "node dropped (poll $i)"; break; fi
done
[ "$DROPPED" = yes ] && LOG "drop confirmed -- the fresh generation is coming" || LOG "reset absorbed (no drop) -- retry later"
cd "$R/wave27-scripts"
cmd.exe /c "$PY timed-ssh-v27.py --deadline-minutes 280 --run-id 20261110-rc$(date +%H%M%S)" > "$R/wave27-scripts/reset-cycle-run.log" 2>&1 &
LOG "hunt relaunched (background)"
