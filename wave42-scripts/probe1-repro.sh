#!/bin/bash
# Wave 42 probe 1: reproduce the -O1 elimination of usb_pair_rebuild on the current
# gen-4+hardening source, and calibrate against the gen-3 backup (expected: gen-3
# keeps its rebuild at -O1, per wave38 handoff 4). Ship flags = build.sh +
# PAYLOAD_BASE=0xF4000000 (make-payload-v38.sh line 55).
set -u
mkdir -p /tmp/w42
cd ~/hakios/kernel/xnuloader
FLAGS="--target=aarch64-unknown-windows -ffreestanding -fno-builtin -fno-stack-protector -fshort-wchar -mgeneral-regs-only -O1 -Wall -Wextra -Wno-unused-parameter -DPAYLOAD_BASE=0xF4000000ULL -I."

probe_obj() {  # $1=obj  $2=label
  echo "== $2 =="
  echo "size=$(stat -c%s "$1")"
  echo "-- symbol table entries for usb_pair_rebuild:"
  llvm-objdump -t "$1" | grep -i 'usb_pair_rebuild' || echo "  (no symbol)"
  echo "-- gen-4 strings:"
  for s in 'the pair reads dead in this generation' 'bounded recovery' "the recovery's bring-up is back"; do
    printf '  %-45s -> %s\n' "$s" "$(strings -a "$1" | grep -cF -- "$s")"
  done
}

clang $FLAGS -c loader.c -o /tmp/w42/cur.obj 2>/tmp/w42/cur.err
echo "compile current: rc=$? err=$(wc -c < /tmp/w42/cur.err)B"
probe_obj /tmp/w42/cur.obj "CURRENT loader.c (gen4 + optnone/volatile hardening)"

clang $FLAGS -c loader.c.v38-p01gen3 -o /tmp/w42/g3.obj 2>/tmp/w42/g3.err
echo "compile gen3 backup: rc=$? err=$(wc -c < /tmp/w42/g3.err)B"
echo "== GEN-3 backup (loader.c.v38-p01gen3) =="
echo "size=$(stat -c%s /tmp/w42/g3.obj)"
echo "-- symbol table entries for usb_pair_rebuild:"
llvm-objdump -t /tmp/w42/g3.obj | grep -i 'usb_pair_rebuild' || echo "  (no symbol)"
