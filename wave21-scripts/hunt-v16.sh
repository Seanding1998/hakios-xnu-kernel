#!/bin/bash
# Wave 21.1 v16 hunt, corrected discipline: probe FIRST, re-fresh ONLY after a failed probe.
# (The v15-era habit of detaching every couple of misses killed live serving windows: the
# gadget enumerates and auto-attaches through the persisted binding; if that first pipe is
# dead, one detach->attach revives it -- but a healthy pipe must never be touched.)
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[hunt $(date +%H:%M:%S)] $*"; }

probe() {
  $LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2
}

LOG "watching for a serving window (90 passes x 8 s)"
for i in $(seq 1 90); do
  if lsusb 2>/dev/null | grep -q d00d; then
    R=$(probe)
    if [ -n "$R" ]; then
      LOG "SERVING (pass $i): result=$R"
      if [ "$R" != "running" ]; then
        LOG "idle: oem run (session window 180 s)"
        $LT --timeout 30000 cmd "oem run" 2>/dev/null | grep -q OKAY || LOG "(no clean OKAY)"
        LOG "waiting 50 s for the kernel's survey and en0"
        sleep 50
      fi
      LOG "=== N1: the ring's round trip ==="
      $LT --timeout 60000 netmode --frames 4 --size 96 --seconds 40 --interval 0.02 2>&1 | \
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
      exit 0
    fi
    # visible but the probe died: one fresh attach, then keep probing (never preemptive)
    LOG "pass $i: the gadget is up but the pipe is dead: detach->attach once"
    usbipd.exe detach --busid 2-2 >/dev/null 2>&1
    sleep 2
    usbipd.exe attach --wsl --busid 2-2 >/dev/null 2>&1
    sleep 4
  else
    [ $((i % 15)) -eq 0 ] && LOG "pass $i: dark (the loader is cycling; the gadget auto-attaches when it enumerates)"
  fi
  sleep 8
done
LOG "90 passes without a serving loader: no verdict this round"
exit 2
