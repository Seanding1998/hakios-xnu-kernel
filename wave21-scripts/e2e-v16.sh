#!/bin/bash
# Wave 21.1 v16 end-to-end: hunt for a boot whose USB server came up, then N1 -> N2 -> N3.
# The v16 loader gives the platform five quiet seconds after the init event before the first
# start_ex (the delayed first try), so the serving window should open on most boots now.
# F7 discipline kept: every second probe miss starts from a FRESH usbipd detach->attach (the
# stale export silently swallowed writes in v15's rounds).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[v16 $(date +%H:%M:%S)] $*"; }

fresh() {
  usbipd detach --busid 2-2 >/dev/null 2>&1
  sleep 2
  usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  sleep 4
  lsusb 2>/dev/null | grep -q d00d
}

LOG "waiting for the loader gadget (up to 5 min)"
for i in $(seq 1 60); do
  if usbipd list 2>/dev/null | grep -q "18d1:d00d"; then
    if fresh; then LOG "gadget fresh in WSL (pass $i)"; break; fi
  fi
  sleep 5
done
usbipd list 2>/dev/null | grep -q "18d1:d00d" || LOG "no gadget on the bus yet (the loader may be between cycles)"

LOG "polling for a serving window: 70 passes, fresh attach every 2 misses"
SERVED=""
MISS=0
for i in $(seq 1 70); do
  R=$($LT --timeout 6000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then SERVED="$R"; LOG "SERVING (pass $i): result=$R"; break; fi
  MISS=$((MISS+1))
  if [ $((MISS % 2)) -eq 0 ]; then
    fresh || LOG "pass $i: fresh attach found no gadget (the loader is dark; cycling)"
  fi
  sleep 5
done

if [ -z "$SERVED" ]; then
  LOG "70 passes without a serving loader: no verdict this round"
  exit 2
fi

if [ "$SERVED" != "running" ]; then
  LOG "idle: oem run (the session's window is 180 s; N1-N3 budget ~150 s)"
  $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q OKAY || LOG "(no clean OKAY)"
  LOG "waiting 55 s for the kernel's survey and en0"
  sleep 55
fi

LOG "=== N1: the ring's round trip ==="
$LT --timeout 60000 netmode --frames 4 --size 96 --seconds 45 --interval 0.02 2>&1 | \
  grep -E "netstat|loopback|N1 verdict" || LOG "N1: no verdict lines"

LOG "=== N2: ICMP 10.0.0.2 ==="
$LT --timeout 60000 ping 10.0.0.2 --count 5 --interval 1.0 2>&1 | \
  grep -E "reply|N2 verdict" || LOG "N2: no verdict lines"

LOG "=== N3: ssh root@10.0.0.2 ==="
cp $W/id_ed25519_phk110 ~/.ssh/w21_key 2>/dev/null || true
chmod 600 ~/.ssh/w21_key
ssh -i ~/.ssh/w21_key -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -o ProxyCommand="sudo -n python3 -I $W/loader_talk.py --timeout 60000 tunnel 10.0.0.2 22" \
    -o ConnectTimeout=60 root@10.0.0.2 "uname -a; ls /; echo; echo WAVE21-SSH-OK" 2>&1 | \
    grep -vE "^Warning: Permanently added" | tail -30 || LOG "N3: no shell"

LOG "=== the session's log ==="
$LT --timeout 60000 cmd "oem netmode off" 2>/dev/null | grep -q OKAY || true
$LT --timeout 60000 log --out $W/session-log-v16.log 2>/dev/null | head -2 || true
LOG "E2E complete"
