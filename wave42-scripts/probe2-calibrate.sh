#!/bin/bash
# Wave 42 probe 2: gen-3 calibration (-x c for the extensionless-ish backup name) +
# disassembly of the current obj's usb_pair_rebuild stub + its caller's call site.
set -u
mkdir -p /tmp/w42
cd ~/hakios/kernel/xnuloader
FLAGS="--target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mgeneral-regs-only -O1 -Wall -Wextra -Wno-unused-parameter -DPAYLOAD_BASE=0xF4000000ULL -I. -w"

clang $FLAGS -x c -c loader.c.v38-p01gen3 -o /tmp/w42/g3.obj 2>/tmp/w42/g3.err
echo "compile gen3: rc=$? err=$(wc -c < /tmp/w42/g3.err)B"
echo "== GEN-3 usb_pair_rebuild symbol =="
llvm-objdump -t /tmp/w42/g3.obj | grep -i 'usb_pair_rebuild' || echo '  (no symbol)'
echo "-- gen-3 rebuild detector strings:"
for s in 'zombie' 'unread'; do
  printf '  %-20s -> %s\n' "$s" "$(strings -a /tmp/w42/g3.obj | grep -cF -- "$s")"
done

echo "== CURRENT: disassembly around usb_pair_rebuild (0xe118) =="
llvm-objdump -d /tmp/w42/cur.obj --start-address=0xe118 --stop-address=0xe140 2>/dev/null | tail -15
echo "== CURRENT: who calls (references) 0xe118? =="
llvm-objdump -d /tmp/w42/cur.obj 2>/dev/null | grep -nE 'bl?\s+0xe118|0xe118' | head -5
echo "== CURRENT: size of the section at 0xe118 (next symbol) =="
llvm-objdump -t /tmp/w42/cur.obj | grep -A3 'usb_pair_rebuild$' | head -6
