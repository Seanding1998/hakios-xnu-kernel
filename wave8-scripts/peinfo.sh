#!/bin/bash
# Wave8: PE header info + disassembly prep for udon USB drivers
B=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave8-scripts
D="$HOME/hakios/uefi-udon/Binaries/udon/QcomPkg/Drivers"
mkdir -p /tmp/wave8
for f in UsbConfigDxe/UsbConfigDxe.patched.efi UsbConfigDxe/UsbConfigDxe.efi UsbDeviceDxe/UsbDeviceDxe.efi UsbInitDxe/UsbInitDxe.efi UsbfnDwc3Dxe/UsbfnDwc3Dxe.efi; do
  n=$(echo "$f" | tr / _)
  cp "$D/$f" /tmp/wave8/"$n"
  echo "=== $n ==="
  llvm-objdump -h /tmp/wave8/"$n" 2>/dev/null | head -12
done
