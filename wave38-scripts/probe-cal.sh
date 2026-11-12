#!/bin/bash
# Calibration probe: grep -a vs strings on the fresh /OPT:NOREF build.
set -u
mkdir -p /tmp/w38test
cd /home/cyrux/hakios/kernel/xnuloader
PAYLOAD_BASE=0xF4000000 ./build.sh > /tmp/w38test/build.log 2>&1
echo "build rc=$? efi=$(stat -c%s loader.efi 2>/dev/null)"
for s in 'reads dead' 'the IN gate is up' 'checkpoint-1' 'bounded recovery' 'usb: started' 'display budget'; do
  printf '%-24s -> grep-a:%s strings:%s\n' "$s" \
    "$(grep -acF -- "$s" loader.efi)" \
    "$(strings -a loader.efi | grep -cF -- "$s")"
done
echo "== the obj, same probes =="
for s in 'reads dead' 'the IN gate is up' 'bounded recovery'; do
  printf '%-24s -> obj grep-a:%s\n' "$s" "$(grep -acF -- "$s" loader.obj)"
done
