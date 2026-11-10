#!/bin/bash
# Wave8: UsbDeviceOpenProtocols + entry region
llvm-objdump -d --no-show-raw-insn --start-address=0x154c --stop-address=0x1720 /tmp/wave8/UsbDeviceDxe_UsbDeviceDxe.efi 2>/dev/null | tail -90
