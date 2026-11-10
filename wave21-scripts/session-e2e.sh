#!/bin/bash
# Wave 21: one full session's end-to-end sequence, once the loader's gadget is up.
# Rules learned in the first attempts (session 3):
#   - a command whose reply is not read wedges the loader's usb_wait (no timeout when the
#     kernel is not running): every send here is paired with a patient read (timeout 60 s);
#   - during the early boot (the storage survey, ~40 s) the loader does not poll USB at all:
#     nothing is sent between "oem run" and the first fast getvar;
#   - the kernel's own session is 300 s (loader_return_after); the steps are timed to fit:
#     t0 "oem run" -> +50 s en0 should be up -> N1 -> N2 -> N3 -> the log.
set -e
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[session $(date +%H:%M:%S)] $*"; }

# 1. wait for the gadget to answer a command at all (it answers fast once the command loop runs)
LOG "waiting for the loader to answer getvar (up to 3 min)..."
ANSWERED=""
for i in $(seq 1 60); do
  if $LT --timeout 8000 cmd getvar:product 2>/dev/null | grep -q "^payload"; then
    ANSWERED=yes
    LOG "the loader answers (pass $i)"
    break
  fi
  sleep 3
done
[ -n "$ANSWERED" ] || { LOG "the loader never answered: give up this round"; exit 1; }

# 2. what state: a result of "running" means the session is live right now
RES=$($LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2 || true)
LOG "result: $RES"

if [ "$RES" != "running" ]; then
  # post-session: start a fresh one, then wait out the boot's survey quietly
  LOG "starting a fresh session (oem run)"
  $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q OKAY || { LOG "oem run failed"; exit 1; }
  LOG "kernel is coming up; waiting 55 s (the survey does not poll USB)"
  sleep 55
  $LT --timeout 60000 cmd getvar:result 2>/dev/null | grep -q running || {
    LOG "the kernel did not report running; fetching what the log has"
    $LT --timeout 60000 log --out $W/session-log-early.log 2>/dev/null | tail -3
    exit 1
  }
  LOG "session is live"
else
  LOG "a session is already live: using it (its remaining time is unknown)"
fi

# 3. N1: the ring's loopback (en0 answers once its driver is up; poll up to 90 s)
LOG "N1: the ring's round trip"
$LT --timeout 60000 netmode --frames 4 --size 96 --seconds 100 --interval 0.02 2>&1 | \
  grep -E "netstat|loopback|N1 verdict|netmode" || LOG "N1: no verdict lines"

# 4. N2: ICMP echo to 10.0.0.2
LOG "N2: ICMP echo over the bridge"
$LT --timeout 60000 ping 10.0.0.2 --count 5 --interval 1.0 2>&1 | \
  grep -E "reply|N2 verdict|netstat" || LOG "N2: no verdict lines"

# 5. N3: the SSH login (the key, in the WSL home with its 600)
LOG "N3: ssh root@10.0.0.2 through the tunnel"
cp HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts/id_ed25519_phk110 ~/.ssh/w21_key 2>/dev/null || true
chmod 600 ~/.ssh/w21_key
ssh -i ~/.ssh/w21_key \
    -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no \
    -o ProxyCommand="sudo -n python3 -I $W/loader_talk.py --timeout 60000 tunnel 10.0.0.2 22" \
    -o ConnectTimeout=60 root@10.0.0.2 "uname -a; ls /; echo; echo WAVE21-SSH-OK" 2>&1 | \
    grep -vE "^Warning: Permanently added" | tail -30 || LOG "N3: ssh did not get a shell"

LOG "fetching the session's log"
$LT --timeout 60000 cmd "oem netmode off" 2>/dev/null | grep -q OKAY || true
$LT --timeout 60000 log --out $W/session-log-final.log 2>/dev/null | tail -2 || true
LOG "done"
