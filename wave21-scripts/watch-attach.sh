# Watch for the xnuloader gadget and attach it to WSL the moment it appears.
while true; do
  LINE=$(usbipd list 2>/dev/null | grep "18d1:d00d" | head -1)
  if [ -n "$LINE" ]; then
    BUSID=$(echo "$LINE" | awk '{print $1}')
    STATE=$(echo "$LINE" | grep -o "Attached" | head -1)
    if [ -z "$STATE" ]; then
      echo "[watcher] $(date +%H:%M:%S) attaching $BUSID"
      usbipd attach --wsl --busid "$BUSID" 2>&1 | tail -1
    fi
  fi
  sleep 2
done
