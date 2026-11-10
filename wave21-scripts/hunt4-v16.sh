#!/bin/bash
# Wave 21.1 v16 hunt #4: the pipe is the whole game.
# Every loader reboot breaks the usbip export; the auto-attach re-fires onto a GONE device
# instance (Windows shows Attached, WSL lsusb sees nothing). Only a detach->attach surgery
# revives it. So: probe; if the device is visible but silent, operate; the moment getvar:result
# answers, run the whole E2E in this shell (the pipe is never surrendered mid-sequence).
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[hunt4 $(date +%H:%M:%S)] $*"; }

served() {
  $LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2
}

LOG "watching (240 passes x 5 s)"
MISSES=0
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
    MISSES=$((MISSES+1))
    LOG "pass $i: visible but silent (miss $MISSES): surgery"
    usbipd.exe detach --busid 2-2 >/dev/null 2>&1
    sleep 2
    usbipd.exe attach --wsl --busid 2-2 >/dev/null 2>&1
    sleep 4
  fi
  sleep 5
done
LOG "240 passes: no serving window caught"
exit 2
