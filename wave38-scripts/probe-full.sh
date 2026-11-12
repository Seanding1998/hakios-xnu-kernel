#!/bin/bash
# Probe 4b: full disassembly with stderr visible; find the usb_command_loop region via
# the known string, and check whether usb_pair_rebuild's body exists anywhere.
set -x
cd /home/cyrux/hakios/kernel/xnuloader
llvm-objdump -d loader.efi > /tmp/w38test/full.dis 2> /tmp/w38test/dis.err
echo "rc=$? disasm=$(wc -l < /tmp/w38test/full.dis) err=$(head -2 /tmp/w38test/dis.err)"
echo "== string symbol =="
llvm-objdump -t loader.efi 2>/dev/null | grep -iE "window|reads_dead|pair" | head -8
echo "== does any code exist past 0xb000 (the fix chain's functions)? =="
grep -c "^b" /tmp/w38test/full.dis
echo "== theusb_pair_rebuild-like stub (mrs x8 CNTFRQ; mrs x8 CNTVCT; ret) occurrences =="
grep -B2 -A1 "mrs	x8, CNTVCT_EL0" /tmp/w38test/full.dis | head -30
