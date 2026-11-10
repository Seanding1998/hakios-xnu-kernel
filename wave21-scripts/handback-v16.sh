#!/bin/bash
# Wave 21.1 handback: catch the bootloader stage of the loader's cycle (getvar product = taro,
# not xnuloader), set slot a active, and reboot the phone to Android. The loader's own fastboot
# server does not implement set_active, so the ABL stage is identified by its product string.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LOG() { echo "[back $(date +%H:%M:%S)] $*"; }

LOG "watching for the ABL stage (60 passes x 6 s)"
for i in $(seq 1 60); do
  if lsusb 2>/dev/null | grep -q d00d; then
    P=$(sudo -n fastboot getvar product 2>&1 | head -2 | tail -1)
    case "$P" in
      *taro*)
        LOG "pass $i: the ABL stage ($P): slot a active + reboot"
        sudo -n fastboot set_active a 2>&1 | tail -1
        sudo -n fastboot reboot 2>&1 | tail -1
        LOG "handback done"
        exit 0
        ;;
      *xnuloader*)
        : ;; # the loader itself: not the handback window
      *)
        LOG "pass $i: visible, product probe: '$P'"
        usbipd.exe detach --busid 2-2 >/dev/null 2>&1
        sleep 1
        usbipd.exe attach --wsl --busid 2-2 >/dev/null 2>&1
        sleep 3
        ;;
    esac
  fi
  sleep 6
done
LOG "60 passes: no ABL window caught"
exit 2
