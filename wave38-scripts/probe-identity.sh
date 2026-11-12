#!/bin/bash
# Probe 5: file identity + rebuild identity for the loader mystery.
set -u
cd /home/cyrux/hakios/kernel/xnuloader
echo "== identity =="
ls -la loader.c loader.obj loader.efi
md5sum loader.c
echo "loader.c mentions of usb_pair_rebuild_fn: $(grep -c usb_pair_rebuild_fn loader.c)"
echo "loader.obj mentions of usb_pair_rebuild_fn: $(grep -ac usb_pair_rebuild_fn loader.obj 2>/dev/null)"
echo "== rebuild fresh =="
rm -f loader.obj loader.efi
PAYLOAD_BASE=0xF4000000 ./build.sh > /tmp/w38test/build.log 2>&1
echo "build rc=$?"
head -6 /tmp/w38test/build.log
ls -la loader.obj loader.efi
echo "fresh obj mentions of usb_pair_rebuild_fn: $(grep -ac usb_pair_rebuild_fn loader.obj 2>/dev/null)"
echo "fresh efi mentions of usb_pair_rebuild_fn: $(grep -ac usb_pair_rebuild_fn loader.efi 2>/dev/null)"
echo "fresh efi mentions of the IN gate line: $(strings -a loader.efi | grep -cF 'the IN gate is up')"
