#!/bin/bash
# Wave8: scan logdump partitions for loader/USB evidence
cd HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/intel/m3-boot1 || exit 1
for f in b8-logdump.bin logdump-head.bin m3-logdump.bin m3-logfs.bin; do
  echo "=== $f ==="
  strings -n 8 "$f" 2>/dev/null | grep -i -E "usb|XNULOADER|platform |payload|started|loader" | head -40
done
