#!/bin/bash
# Wave 42 probe 9: relocation-level assertion on the v35 loader.obj (persisted to repo).
set -e
cd ~/hakios/kernel/xnuloader
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave42-scripts

llvm-objdump -dr loader.obj --start-address=0xd99c --stop-address=0xe19c > "$R/rebuild-dr.dis.log" 2>&1
echo "dis.log lines: $(wc -l < "$R/rebuild-dr.dis.log")"
echo "== relocation symbol histogram inside usb_pair_rebuild =="
grep "IMAGE_REL" "$R/rebuild-dr.dis.log" | sed 's/.*IMAGE_REL_ARM64_[A-Z0-9_]*[[:space:]]*//' | sort | uniq -c | sort -rn
echo "== tail (function end) =="
tail -6 "$R/rebuild-dr.dis.log"
