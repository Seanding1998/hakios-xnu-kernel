#!/bin/bash
# Probe 2: is usb_pair_rebuild's call still in usb_command_loop's emitted code?
set -u
cd /home/cyrux/hakios/kernel/xnuloader
perl -0777 -pe 's/static void\nusb_pair_rebuild\(void\)/void\nusb_pair_rebuild(void)/' \
  loader.c > /tmp/w38test/loader-ns.c
clang --target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector \
  -fshort-wchar -mgeneral-regs-only -O1 -DPAYLOAD_BASE=0xF4000000ULL -I. \
  -c /tmp/w38test/loader-ns.c -o /tmp/w38test/o1ns.obj 2>/dev/null
# usb_command_loop's symbol and extent, then disassemble it and look for calls
ADDR=$(llvm-objdump -t /tmp/w38test/o1ns.obj | grep -E "usb_command_loop" | awk '{print $6}' | head -1)
echo "usb_command_loop at: $ADDR"
START=$((ADDR))
STOP=$((ADDR + 0x600))
llvm-objdump -d /tmp/w38test/o1ns.obj --start-address=$START --stop-address=$STOP > /tmp/w38test/loop.dis 2>/dev/null
grep -cE "bl" /tmp/w38test/loop.dis
grep -E "bl\s+0x" /tmp/w38test/loop.dis | head -20
# does the disassembly reference the string symbol for 'the service window is over'?
grep -E "service_window|window_over|bl\s+0x1140" /tmp/w38test/loop.dis | head -5
