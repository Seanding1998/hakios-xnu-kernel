#!/bin/bash
# Wave8: find xrefs to UsbDevice protocol GUID (file 0xf0b8) in UsbDeviceDxe
grep -n "0xf0b8\|adrp\s*x[0-9]*, 0xf000" /tmp/wave8/devicedxe.dis | head -20
echo "=== StartEx area: find strings xrefs — search for the 'Failed to Start USB Controller' usage ==="
# The string block for UsbDeviceStartEx errors; find the function that loads multiple args then blr via usbfncall
grep -n "blr\s*x8" /tmp/wave8/devicedxe.dis | head -40
