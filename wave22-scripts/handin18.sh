#!/bin/bash
# Wave 22 hand-in sentry (user directive 2026-11-09 ~01:1x): the USER reboots the phone to
# Android themselves; if the phone later shows up in fastboot mode (18d1:d00d, the ABL
# gadget -- "Android" label), that is the USER's hand-in point, and this sentry restores it
# to Android (slot a) over the script channel. The loader's own gadget ("xnuloader" label)
# is left alone. Runs ~2 h.
LOG() { echo "[handin18 $(date +%H:%M:%S)] $*"; }
LOG "=== sentry armed: watching for the user's fastboot hand-in ==="
for i in $(seq 1 480); do
  ST=$(usbipd.exe list 2>/dev/null | grep "2-2 " | head -1)
  case "$ST" in
    *22d9*)
      # Android already: confirm boot_completed then stand down
      export ADB_SERVER_SOCKET=tcp:127.0.0.1:5037
      BC=$(timeout 20 adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')
      if [ "$BC" = "1" ]; then LOG "Android is back (boot_completed=1): sentry stands down"; exit 0; fi
      ;;
    *"18d1:d00d"*"Android"*)
      LOG "the user's fastboot hand-in: $ST"
      usbipd.exe list 2>/dev/null | grep "2-2 " | grep -q Attached || {
        usbipd attach --wsl --busid 2-2 >/dev/null 2>&1
        sleep 3
      }
      P=$(sudo -n fastboot getvar product 2>&1 | head -2 | tail -1)
      case "$P" in
        *taro*)
          LOG "ABL fastboot confirmed ($P): set_active a + reboot"
          sudo -n fastboot set_active a 2>&1 | tail -1
          sudo -n fastboot reboot 2>&1 | tail -1
          LOG "restored to Android-bound slot a; sentry done"
          exit 0
          ;;
        *)
          LOG "not the ABL window (product probe: '$P'); releasing the port"
          usbipd.exe detach --busid 2-2 >/dev/null 2>&1
          ;;
      esac
      ;;
  esac
  sleep 15
done
LOG "sentry expired (2 h) with no hand-in seen"
