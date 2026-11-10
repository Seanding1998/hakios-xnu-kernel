#!/bin/bash
# Wave8: dump full context of the XNULOADER log region in b8-logdump.bin
cd HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/intel/m3-boot1 || exit 1
off=$(grep -abo "== XNULOADER v3 ==" b8-logdump.bin | head -1 | cut -d: -f1)
echo "offset: $off"
if [ -n "$off" ]; then
  dd if=b8-logdump.bin bs=1 skip=$((off > 4096 ? off - 4096 : 0)) count=32768 2>/dev/null | strings -n 4 | head -200
fi
