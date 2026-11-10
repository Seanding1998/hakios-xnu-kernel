pnputil /enum-devices /class USBDevice
pnputil /remove-device "USB\VID_18D1&PID_D00D\XNULOADER"
pnputil /scan-devices
pnputil /enum-devices /class USBDevice
