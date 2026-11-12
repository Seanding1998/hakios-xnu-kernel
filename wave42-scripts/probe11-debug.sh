#!/bin/bash
# Wave 42 probe 11: debug the exact ADRP/ADD pair for the rebuild string.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave42-scripts
echo "== obj-space reloc sites for the five strings (from probe9's -dr log) =="
grep -n -B2 "MGBPICDP" "$R/rebuild-dr.dis.log" | head -20
echo "== is efi_main at obj 0x1140 (shift 0x1000 hypothesis)? =="
cd ~/hakios/kernel/xnuloader
llvm-objdump -t loader.obj | grep -E "efi_main$|usb_pair_rebuild$"
echo "== hexdump the efi around 0xe99c+ (if shift holds: obj d99c + 1000) =="
python3 - <<'EOF'
efi = open('/home/cyrux/hakios/kernel/xnuloader/loader.efi','rb').read()
# .text roff=0x400 va=0x1000 -> file offset = rva - 0x1000 + 0x400
def rva_off(rva): return rva - 0x1000 + 0x400
import struct
for rva in (0xe990, 0xe998, 0xe9a0):
    off = rva_off(rva)
    w = struct.unpack_from('<I', efi, off)[0]
    print(hex(rva), hex(w))
EOF
