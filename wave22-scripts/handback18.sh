#!/bin/bash
# Wave 22 handback: catch the ABL stage of the cycle (getvar product = taro; the loader's
# own gadget answers product=xnuloader and does not implement set_active), set slot a, and
# reboot to Android. If Android appears first (the ABL fallback took the slot), reboot it
# into the bootloader to get the same ABL window. 300 passes x 6 s.
W=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave21-scripts
LOG() { echo "[back18 $(date +%H:%M:%S)] $*"; }

LOG "watching for the ABL stage (300 passes x 6 s)"
for i in $(seq 1 300); do
  ST=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  if echo "$ST" | grep -q "22d9"; then
    LOG "pass $i: Android on the bus; rebooting to the bootloader for the ABL window"
    export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
    timeout 30 adb reboot bootloader 2>/dev/null
    sleep 15
  fi
  if usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q "d00d"; then
    usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q Attached || {
      usbipd.exe attach --wsl --busid 2-2 >/dev/null 2>&1
      sleep 3
    }
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
        *xnuloader*|*"not found"*|*)
          usbipd.exe detach --busid 2-2 >/dev/null 2>&1
          ;;
      esac
    fi
  fi
  sleep 6
done
LOG "300 passes: no ABL window caught"
exit 2
