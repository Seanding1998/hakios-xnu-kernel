#!/bin/bash
K=~/hakios/kernel
echo "===== kernel-side apfs driver location ====="
find $K/xnu-src $K/xnu -name "*apfs*" -name "*.c" 2>/dev/null | head -5
find $K/xnu-src $K/xnu -path "*apfs*" -name "*.h" 2>/dev/null | head -5
echo "===== ,c= parsing in kernel apfs ====="
grep -rn '",c=\|c=%d\|container\|nx_block_count\|NXSB\|nx_superblock' $K/xnu-src/xnu-8796.121.2/bsd/hakios_apfs.c 2>/dev/null | head -20
for f in $(find $K/xnu-src $K/xnu -name "*apfs*" -name "*.c" 2>/dev/null | head -3); do
  echo "--- $f"
  grep -n '",c=\|", c = \|c=\|NX_CONTAINER\|next container\|container at' $f | head -15
done
echo "===== mkapfs.py size/count handling ====="
grep -n "block_count\|nx_block\|blocks\b\|--size\|add_argument\|def main" ~/hakios/kernel/tools/apfs/mkapfs.py | head -25
