#!/bin/bash
# Wave8: find code referencing the init-event GUID (0x17048) in UsbConfigDxe dis
grep -n "17048\|0x17040\|adrp.*0x17000" /tmp/wave8/configdxe.patched.dis | head -20
echo "=== patched-vs-unpatched at 0x5348 ==="
llvm-objdump -d --no-show-raw-insn --start-address=0x5300 --stop-address=0x53a0 /tmp/wave8/UsbConfigDxe_UsbConfigDxe.patched.efi 2>/dev/null | tail -30
echo "=== unpatched ==="
llvm-objdump -d --no-show-raw-insn --start-address=0x5300 --stop-address=0x53a0 /tmp/wave8/UsbConfigDxe_UsbConfigDxe.efi 2>/dev/null | tail -30
