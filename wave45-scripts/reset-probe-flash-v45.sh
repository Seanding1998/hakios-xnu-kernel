sudo -n sh -c 'echo 0 > /sys/bus/usb/devices/1-1/authorized'
sleep 3
sudo -n sh -c 'echo 1 > /sys/bus/usb/devices/1-1/authorized'
sleep 2
for i in 1 2 3 4 5 6 7 8 9 10; do
  lsusb | grep -q 18d1 && break
  sleep 1
done
lsusb | grep 18d1
sudo -n fastboot getvar product 2>&1 | head -2
sudo -n fastboot getvar current-slot 2>&1 | head -2
