#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
echo "== payload $(date -Is)"
CMDLINE="soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws"
echo "cmdline length: ${#CMDLINE}"
xnuloader/mkpayload.py -o run-payload.bin \
  loader.efi=xnuloader/loader.efi \
  kernel=hakios-kernel \
  ramdisk=userland/hello \
  --cmdline "$CMDLINE"
echo "== payload entries:"
python3 - run-payload.bin << 'PY'
import struct, sys
data = open(sys.argv[1], 'rb').read()
magic, size = struct.unpack_from('<II', data)
print(f'payload magic={magic:08x} (expect 50554e58) declared_size={size} file_size={len(data)}')
off = 8
while off + 24 <= len(data):
    name, esize, res = struct.unpack_from('<16sII', data, off)
    name = name.rstrip(b'\0').decode()
    if name == '':
        print('  <end entry>'); break
    print(f'  entry {name!r}: {esize} bytes')
    off += 24 + (esize + 15) // 16 * 16
PY
echo "== mkxnuimg $(date -Is)"
./mkxnuimg.py --device phk110 --fd-base 0xA7100000 --fd-size 0x300000 --payload-base 0xC0000000 \
  -p run-payload.bin -o xnu-phk110.img
echo "== verify $(date -Is)"
python3 - xnu-phk110.img << 'PY'
import struct, sys, gzip, zlib
data = open(sys.argv[1], 'rb').read()
magic = data[:8]
hdr = struct.unpack_from('<8s9I', data, 0)
(_, ksz, kaddr, rsz, raddr, ssz, saddr, tags, page, hver) = hdr
print(f'boot magic={magic!r} (expect b"ANDROID!") total={len(data)} page_size={page} header_version={hver}')
print(f'kernel_size={ksz} ramdisk_size={rsz} second_size={ssz}')
kern = data[page:page+ksz]
rd   = data[page+ksz:page+ksz+rsz]
print(f'ramdisk bytes: {rd!r} (expect b"dummy")')
blob = gzip.decompress(kern)
print(f'gunzipped kernel blob: {len(blob)} bytes')
FD_BASE, FD_SIZE, PAYLOAD_BASE = 0xA7100000, 0x300000, 0xC0000000
# find shim end: shim is tiny (112 B class); locate "XNUP" in blob
xnup = blob.find(b'XNUP')
print(f'"XNUP" container at blob offset {xnup:#x}')
# FD magic: EFI FV zero vector then _FVH signature at +40
fvh = blob.find(b'_FVH')
print(f'EFI FVH signature at blob offset {fvh:#x} (FD starts ~{fvh-40:#x})')
assert xnup > 0 and fvh > 0
print('kernel blob structure OK')
PY
echo "== sha256:"
sha256sum xnu-phk110.img run-payload.bin Mu-Silicium/Build/phk110Pkg/RELEASE_CLANGPDB/FV/SILICIUM_UEFI.fd Mu-Silicium/BootShim/BootShim.bin
ls -la xnu-phk110.img
echo "== done $(date -Is)"
