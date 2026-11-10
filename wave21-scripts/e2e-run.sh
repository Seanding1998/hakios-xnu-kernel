#!/bin/bash
# Poll the loader until it serves (v15.3's lazy bring-up succeeds), then run the full E2E.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[e2e $(date +%H:%M:%S)] $*"; }

LOG "polling for a serving loader (up to 8 min)"
SERVED=""
for i in $(seq 1 40); do
  R=$($LT --timeout 12000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then
    SERVED="$R"
    LOG "SERVING (pass $i): result=$R"
    break
  fi
  D=$(lsusb 2>/dev/null | grep -c d00d)
  if [ "$D" = "0" ] && usbipd list 2>/dev/null | grep -q "2-2"; then
    usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
  fi
  sleep 12
done
[ -n "$SERVED" ] || { LOG "the loader never served"; exit 1; }

if [ "$SERVED" != "running" ]; then
  LOG "idle: starting the session"
  $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q "OKAY" || LOG "(oem run: no clean OKAY; continuing)"
  LOG "waiting 60 s (the storage survey does not poll USB)"
  sleep 60
fi

LOG "=== N1: the ring's round trip ==="
$LT --timeout 60000 netmode --frames 4 --size 96 --seconds 60 --interval 0.02 2>&1 | \
  grep -E "netstat|loopback|N1 verdict" || LOG "N1: no verdict lines"

LOG "=== N2: ICMP echo 10.0.0.2 ==="
$LT --timeout 60000 ping 10.0.0.2 --count 5 --interval 1.0 2>&1 | \
  grep -E "reply|N2 verdict" || LOG "N2: no verdict lines"

LOG "=== N3: ssh root@10.0.0.2 ==="
cp $W/id_ed25519_phk110 ~/.ssh/w21_key 2>/dev/null || true
chmod 600 ~/.ssh/w21_key
ssh -i ~/.ssh/w21_key -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -o ProxyCommand="sudo -n python3 -I $W/loader_talk.py --timeout 60000 tunnel 10.0.0.2 22" \
    -o ConnectTimeout=60 root@10.0.0.2 "uname -a; ls /; echo; echo WAVE21-SSH-OK" 2>&1 | \
    grep -vE "^Warning: Permanently added" | tail -30 || LOG "N3: ssh did not get a shell"

LOG "=== the session's log ==="
$LT --timeout 60000 cmd "oem netmode off" 2>/dev/null | grep -q OKAY || true
$LT --timeout 60000 log --out $W/session-log-final.log 2>/dev/null | head -2 || true
LOG "E2E done"
