#!/bin/bash
# The disciplined final E2E: every probe round starts from a FRESH usbipd attach (the stale
# export was the trap -- the phone re-enumerates and the old WSL pipe silently swallows writes).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[final $(date +%H:%M:%S)] $*"; }

fresh() {
  usbipd detach --busid 2-2 >/dev/null 2>&1
  sleep 2
  usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  sleep 4
  lsusb 2>/dev/null | grep -q d00d
}

LOG "waiting for the gadget (up to 4 min)"
for i in $(seq 1 48); do
  if usbipd list 2>/dev/null | grep -q "18d1:d00d"; then
    if fresh; then LOG "gadget fresh in WSL (pass $i)"; break; fi
  fi
  sleep 5
done

LOG "polling getvar for a serving window (fresh attach every 3 misses)"
SERVED=""
for i in $(seq 1 20); do
  R=$($LT --timeout 6000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then SERVED="$R"; LOG "SERVING (pass $i): result=$R"; break; fi
  if ! fresh; then LOG "pass $i: the gadget dropped; re-freshing"; continue; fi
  sleep 3
done
[ -n "$SERVED" ] || { LOG "never served: give up"; exit 1; }

if [ "$SERVED" != "running" ]; then
  LOG "idle: oem run"
  $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q "OKAY" || LOG "(no clean OKAY)"
  LOG "waiting 55 s for en0 (survey does not poll USB)"
  sleep 55
fi

LOG "=== N1: ring round trip ==="
$LT --timeout 60000 netmode --frames 3 --size 96 --seconds 45 --interval 0.02 2>&1 | \
  grep -E "netstat|loopback|N1 verdict" || LOG "N1: no verdict lines"

LOG "=== N2: ICMP 10.0.0.2 ==="
$LT --timeout 60000 ping 10.0.0.2 --count 4 --interval 1.0 2>&1 | \
  grep -E "reply|N2 verdict" || LOG "N2: no verdict lines"

LOG "=== N3: ssh root@10.0.0.2 ==="
cp $W/id_ed25519_phk110 ~/.ssh/w21_key 2>/dev/null || true
chmod 600 ~/.ssh/w21_key
ssh -i ~/.ssh/w21_key -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -o ProxyCommand="sudo -n python3 -I $W/loader_talk.py --timeout 60000 tunnel 10.0.0.2 22" \
    -o ConnectTimeout=60 root@10.0.0.2 "uname -a; ls /; echo; echo WAVE21-SSH-OK" 2>&1 | \
    grep -vE "^Warning: Permanently added" | tail -30 || LOG "N3: no shell"

LOG "=== session log ==="
$LT --timeout 60000 cmd "oem netmode off" 2>/dev/null | grep -q OKAY || true
$LT --timeout 60000 log --out $W/session-log-final.log 2>/dev/null | head -2 || true
LOG "E2E complete"
