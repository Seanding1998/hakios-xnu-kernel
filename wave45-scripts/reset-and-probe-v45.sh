if [ ! -e /sys/bus/usb/devices/1-1/authorized ]; then echo "no 1-1"; exit 1; fi
echo 0 > /sys/bus/usb/devices/1-1/authorized
sleep 2
echo 1 > /sys/bus/usb/devices/1-1/authorized
sleep 1
for i in 1 2 3 4 5 6 7 8; do
  if lsusb | grep -q 18d1:d00d; then break; fi
  sleep 1
done
lsusb | grep 18d1
fastboot getvar product 2>&1 | head -2
