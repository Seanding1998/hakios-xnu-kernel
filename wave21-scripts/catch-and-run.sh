#!/bin/bash
# Wave 21.2: catch a serving boot and run the whole E2E -- N1 (ring loopback) -> N2 (ICMP)
# -> N3 (ssh into the Darwin shell), with the pipe guardian as the default behavior.
#
# The guardian lives inside loader_talk.py now (the hunt5 paradigm made default): before every
# operation it self-checks the usbipd/WSL pipe; the F9 dead-export signature (Windows shows
# the device, WSL cannot see it) is cured by one detach->attach surgery per device generation;
# a generation that stays visible but never answers gets the same single cure only after the
# loader's boot-time tries are spent (v16b: 25/50/75 s, ~52 s past the generation's first
# sight); every surgery is followed by a random 4-9 s pause clear of the loader's start
# window. This script therefore probes purely -- no surgeries here.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[catch $(date +%H:%M:%S)] $*"; }

SERVED=""
for i in $(seq 1 200); do
  # the timeout wrapper is load-bearing: a wedged usbip/vhci pipe can stall a probe forever
  # (libusb_set_configuration has no libusb-level timeout); a stalled probe must not pin the
  # loop -- the guardian gets its turn on the next pass and cures the pipe.
  R=$(timeout 40 $LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
  if [ -n "$R" ]; then
    SERVED="$R"
    LOG "the loader serves (pass $i): result=$R"
    break
  fi
  sleep 5
done

if [ -z "$SERVED" ]; then
  LOG "200 passes without a serving loader: no verdict this round"
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
$LT --timeout 60000 log --out $W/session-log-v16b.log 2>/dev/null | head -2 || true
LOG "E2E complete"
