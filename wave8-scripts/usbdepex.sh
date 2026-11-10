#!/bin/bash
# Wave8 scratch: dump depex + protocol refs of udon USB drivers
for f in UsbInitDxe UsbConfigDxe UsbDeviceDxe UsbfnDwc3Dxe UsbPwrCtrlDxe; do
  d="$HOME/hakios/uefi-udon/Binaries/udon/QcomPkg/Drivers/$f"
  echo "=== $f INF ==="
  cat "$d/$f.inf"
  echo "=== $f depex hex ==="
  xxd "$d/$f.depex" 2>/dev/null
  echo
done
