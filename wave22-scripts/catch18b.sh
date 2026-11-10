#!/bin/bash
# Wave 22 round-2 catch: the persistent sampler. Boot #36's logdump proved the loader side
# (present -> gen 0 beat 1 ARMED -> full session); round 1's catch had already exhausted its
# 200 fast passes (24 min) by the time the armed sessions came, and the one live probe raced
# a guardian surgery. This round: 1200 passes (~1.5-2 h, the loader is already on boot_b --
# no flash needed), the full E2E on the first serving pass, and a running log so the
# exhaustion case is precisely attributable.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[catch18b $(date +%H:%M:%S)] $*"; }

SERVED=""
for i in $(seq 1 1200); do
  R=$(timeout 40 $LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then
    SERVED="$R"
    LOG "the loader serves (pass $i): result=$R"
    break
  fi
  if [ $((i % 15)) -eq 0 ]; then LOG "pass $i: not served yet"; fi
  sleep 3
done

if [ -z "$SERVED" ]; then
  LOG "1200 passes without a serving loader: no verdict this round"
  exit 2
fi

if [ "$SERVED" != "running" ]; then
  LOG "idle: oem run (the session's window is 180 s; the N1-N3 budget is ~150 s)"
  $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q OKAY || LOG "(no clean OKAY)"
  LOG "waiting 55 s for the kernel's survey and en0"
  sleep 55
else
  LOG "a session is already live: straight to N1"
fi

LOG "=== N1: the ring's round trip ==="
$LT --timeout 60000 netmode --frames 4 --size 96 --seconds 45 --interval 0.02 2>&1 | \
  grep -E "netstat|loopback|N1 verdict" || LOG "N1: no verdict lines"

LOG "=== N2: ICMP echo 10.0.0.2 ==="
$LT --timeout 60000 ping 10.0.0.2 --count 5 --interval 1.0 2>&1 | \
  grep -E "reply|N2 verdict" || LOG "N2: no verdict lines"

LOG "=== N3: ssh root@10.0.0.2 (the Darwin shell) ==="
cp $W/id_ed25519_phk110 ~/.ssh/w21_key 2>/dev/null || true
chmod 600 ~/.ssh/w21_key
SSH_OUT=$(ssh -i ~/.ssh/w21_key -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -o ProxyCommand="sudo -n python3 -I $W/loader_talk.py --timeout 60000 tunnel 10.0.0.2 22" \
    -o ConnectTimeout=60 root@10.0.0.2 "uname -a; echo ---; ls /; echo ---; echo WAVE21-SSH-OK" 2>&1)
echo "$SSH_OUT" | grep -vE "^Warning: Permanently added"
if echo "$SSH_OUT" | grep -q "WAVE21-SSH-OK"; then
  LOG "N3 VERDICT: PASS -- a Darwin shell answered over the loader's channel"
else
  LOG "N3: no shell this round"
fi

LOG "=== the session's log ==="
$LT --timeout 60000 cmd "oem netmode off" 2>/dev/null | grep -q OKAY || true
$LT --timeout 60000 log --out $W/session-log-v18.log 2>/dev/null | head -2 || true
LOG "E2E complete"
