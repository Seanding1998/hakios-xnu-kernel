for i in $(seq 1 25); do
  if ls /sys/bus/usb/devices/ | grep -q "^1-1$"; then
    echo "FOUND at poll $i"; lsusb; break
  fi
  sleep 1
done
ls /sys/bus/usb/devices/
