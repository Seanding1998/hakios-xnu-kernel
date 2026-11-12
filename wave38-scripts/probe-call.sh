#!/bin/bash
# Probe 3: usb_command_loop's emitted code — is the usb_pair_rebuild call present?
set -u
cd /home/cyrux/hakios/kernel/xnuloader
echo "== symbols containing command_loop / pair_rebuild / optnone stubs:"
llvm-objdump -t loader.efi 2>/dev/null | grep -iE "command_loop|pair_rebuild" | head -5
ADDR=$(llvm-objdump -t loader.efi 2>/dev/null | grep -E "usb_command_loop" | awk '{print $6}' | head -1)
echo "usb_command_loop at: ${ADDR:-<none>}"
if [ -n "$ADDR" ]; then
  START=$((ADDR))
  STOP=$((ADDR + 0x400))
  llvm-objdump -d loader.efi --start-address=$START --stop-address=$STOP > /tmp/w38test/loop.dis 2>/dev/null
  echo "branch instructions in usb_command_loop:"
  grep -E "\bbl\b" /tmp/w38test/loop.dis | head -16
fi
