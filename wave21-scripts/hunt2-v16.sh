#!/bin/bash
# Wave 21.1 v16 hunt #2: identify who is on the wire before acting.
# 18d1:d00d shows up as TWO different talkers per cycle: the ABL fastboot stage (~20-30 s,
# getvar:product = taro) and the loader's serving window (minutes, getvar:product = xnuloader).
# Only a xnuloader answering getvar:result goes to N1 -> N2 -> N3. A dead pipe gets exactly one
# detach->attach surgery, with usbipd's own output logged this time.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LT="sudo -n python3 -I $W/loader_talk.py"
LOG() { echo "[hunt2 $(date +%H:%M:%S)] $*"; }

LOG "watching (120 passes x 5 s)"
for i in $(seq 1 120); do
  if lsusb 2>/dev/null | grep -q d00d; then
    P=$($LT --timeout 8000 cmd getvar:product 2>&1 | grep -v "^DEVICE ERROR" | head -1)
    case "$P" in
      *xnuloader*)
        R=$($LT --timeout 8000 cmd getvar:result 2>/dev/null | grep "^payload" | cut -d"'" -f2)
        LOG "pass $i: THE LOADER IS SERVING (product=xnuloader, result=$R)"
        if [ "$R" != "running" ]; then
          LOG "idle: oem run"
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
        ;;
      *taro*)
        : ;; # the ABL stage: wait it out
      "")
        LOG "pass $i: d00d visible but the pipe answers nothing: surgery"
        usbipd.exe detach --busid 2-2 2>&1 | head -1
        sleep 2
        usbipd.exe attach --wsl --busid 2-2 2>&1 | head -1
        sleep 4
        ;;
      *)
        LOG "pass $i: on the wire: $P"
        ;;
    esac
  fi
  sleep 5
done
LOG "120 passes: no serving window caught"
exit 2
