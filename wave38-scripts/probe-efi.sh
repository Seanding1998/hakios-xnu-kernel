#!/bin/bash
# Probe 6: dump efi_main's emitted loop region — is the volatile recovery call there?
set -u
mkdir -p /tmp/w38test
cd /home/cyrux/hakios/kernel/xnuloader
PAYLOAD_BASE=0xF4000000 ./build.sh > /tmp/w38test/build.log 2>&1
echo "build rc=$? efi=$(stat -c%s loader.efi 2>/dev/null) obj=$(stat -c%s loader.obj 2>/dev/null)"
echo "obj mentions usb_pair_rebuild_fn: $(grep -ac usb_pair_rebuild_fn loader.obj)"
echo "obj relocations to usb_pair_rebuild: $(grep -ac usb_pair_rebuild loader.obj)"
# find efi_main symbol
ADDR=$(llvm-objdump -t loader.efi 2>/dev/null | grep -E " efi_main$" | awk '{print $6}' | head -1)
echo "efi_main at: ${ADDR:-none}"
# find the string symbol for the service-window line
SSYM=$(llvm-objdump -t loader.efi 2>/dev/null | grep -iE "service\?5window\?5is\?5over" | awk '{print $6}' | head -1)
echo "service-window string symbol: ${SSYM:-none}"
if [ -n "$ADDR" ] && [ -n "$SSYM" ]; then
  START=$((16#$ADDR))
  STOP=$((START + 0x3000))
  llvm-objdump -d loader.efi --start-address=$START --stop-address=$STOP > /tmp/w38test/efi.dis 2>/dev/null
  grep -n "$SSYM" /tmp/w38test/efi.dis | head -3
  LN=$(grep -n "$SSYM" /tmp/w38test/efi.dis | head -1 | cut -d: -f1)
  if [ -n "$LN" ]; then
    S=$((LN - 40)); [ $S -lt 1 ] && S=1
    E=$((LN + 120))
    sed -n "${S},${E}p" /tmp/w38test/efi.dis
  fi
fi
