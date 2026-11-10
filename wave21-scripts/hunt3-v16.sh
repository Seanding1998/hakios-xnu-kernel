#!/bin/bash
# Wave 21.1 v16 hunt #3: the classifier fixed -- the loader's answer line is matched across the
# WHOLE probe output (loader_talk prints a descriptor dump before every answer), never head -1.
# Probe getvar:result every 5 s; the moment it answers, run the whole E2E in this same shell so
# the live pipe is never surrendered between the catch and the N1->N2->N3 sequence.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[hunt3 $(date +%H:%M:%S)] $*"; }

served() {
  $LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2
}

LOG "watching (240 passes x 5 s = 20 min)"
SEEN=0
for i in $(seq 1 240); do
  if lsusb 2>/dev/null | grep -q d00d; then
    R=$(served)
    if [ -n "$R" ]; then
      LOG "THE LOADER SERVES (pass $i): result=$R"
      if [ "$R" = "running" ]; then
        LOG "a session is already live: straight to N1"
      else
        LOG "idle: oem run"
        $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q OKAY || LOG "(no clean OKAY)"
        LOG "waiting 50 s for the kernel's survey and en0"
        sleep 50
      fi
      LOG "=== N1: the ring's round trip ==="
      $LT --timeout 60000 netmode --frames 4 --size 96 --seconds 40 --interval 0.02 2>&1 | \
        grep -E "netstat|loopback|N1 verdict|frames" || LOG "N1: no verdict lines"
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
      exit 0
    fi
    SEEN=$((SEEN+1))
    [ $((SEEN % 24)) -eq 0 ] && LOG "pass $i: the gadget is up ($SEEN looks) but no serving answer yet"
  fi
  sleep 5
done
LOG "240 passes: no serving window caught"
exit 2
