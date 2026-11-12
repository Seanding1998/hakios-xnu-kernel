#!/bin/bash
# Wave 42 probe 3: find the exact LLVM pass that empties usb_pair_rebuild's body.
# -print-after-all filtered to usb_pair_rebuild; report the pass sequence and where
# the body loses its blocks.
set -u
mkdir -p /tmp/w42
cd ~/hakios/kernel/xnuloader
FLAGS="--target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mgeneral-regs-only -O1 -w -DPAYLOAD_BASE=0xF4000000ULL -I."

clang $FLAGS -c loader.c -o /tmp/w42/pf.obj \
  -mllvm -print-after-all -mllvm -filter-print-funcs=usb_pair_rebuild \
  2>/dev/null > /tmp/w42/afterall.log
echo "log bytes: $(stat -c%s /tmp/w42/afterall.log)"
echo "== pass sequence (headers) =="
grep -c 'IR Dump' /tmp/w42/afterall.log
grep 'IR Dump' /tmp/w42/afterall.log | head -60
