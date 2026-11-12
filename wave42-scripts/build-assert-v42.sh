#!/bin/bash
# Wave 42: the REAL v35 loader build (ship recipe: PAYLOAD_BASE=0xF4000000 ./build.sh)
# followed by the obj/disassembly-level assertion that usb_pair_rebuild is real.
set -e
cd ~/hakios/kernel/xnuloader
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110

echo "== build (ship recipe) =="
PAYLOAD_BASE=0xF4000000 ./build.sh
sha256sum loader.c loader.obj loader.efi

echo "== obj-level: symbol + size =="
llvm-nm -S loader.obj 2>/dev/null | grep -i usb_pair_rebuild || llvm-objdump -t loader.obj | grep -i usb_pair_rebuild

echo "== obj-level: relocations proving the recovery's five print strings are referenced =="
llvm-objdump -r loader.obj 2>/dev/null > /tmp/w42/relocs.txt
for sym in 'MGBPICDP' 'PEFDBFNM' 'FKMJAFGM' 'GDAEMIE' 'HLNHMHIM'; do
  printf '  %s -> %s relocs\n' "$sym" "$(grep -c "$sym" /tmp/w42/relocs.txt)"
done

echo "== obj-level: disassembly of usb_pair_rebuild =="
ADDR=$(llvm-objdump -t loader.obj | grep -E 'sec  1.*usb_pair_rebuild$' | awk '{print $5}' | head -1)
echo "usb_pair_rebuild at $(LC_ALL=C printf '0x%x' "${ADDR}")"
END=$(python3 -c "print(hex(${ADDR} + 0x400))")
llvm-objdump -d loader.obj --start-address="$ADDR" --stop-address="$END" 2>/dev/null > /tmp/w42/rebuild.dis
wc -l /tmp/w42/rebuild.dis
cp /tmp/w42/rebuild.dis "$R/wave42-scripts/rebuild.dis.log"
grep -cE 'mrs' /tmp/w42/rebuild.dis
echo "-- bl/blr calls in the body:"
grep -E '\b(bl|blr)\b' /tmp/w42/rebuild.dis | head -20
