#!/bin/bash
set -e
cd /home/HOST-REDACTED/hakios/kernel
CMDLINE="serial=0 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws"
echo "cmdline length: ${#CMDLINE}"
xnuloader/mkpayload.py -o run-payload.bin \
  loader.efi=xnuloader/loader.efi \
  kernel=hakios-kernel \
  ramdisk=userland/hello \
  --cmdline "$CMDLINE"
./mkxnuimg.py --device phk110 --fd-base 0xA7100000 --fd-size 0x300000 --payload-base 0xC0000000 \
  -p run-payload.bin -o xnu-phk110.img
python3 - xnu-phk110.img << 'PY'
import struct, sys, gzip
data = open(sys.argv[1], 'rb').read()
(_, ksz, kaddr, rsz, raddr, ssz, saddr, tags, page, hver) = struct.unpack_from('<8s9I', data, 0)
kern = data[page:]
blob = gzip.decompress(kern[:kern.find(b'\xd0\x0d\xfe\xed')])
xnup = blob.find(b'XNUP')
size = struct.unpack_from('<I', blob, xnup+4)[0]
# extract cmdline entry to confirm serial=0 present
off = xnup + 8
while off + 24 <= len(blob):
    name, esize, _ = struct.unpack_from('<16sII', blob, off)
    name = name.rstrip(b'\0').decode()
    if name == '':
        break
    if name == 'cmdline':
        print(f'cmdline in image ({esize} bytes): {blob[off+24:off+24+esize].decode(errors="replace")!r}')
    off += 24 + (esize + 15) // 16 * 16
print(f'final check: magic={data[:8]!r} size={len(data)} kernel_size={ksz} shim_fdbase={blob[8:12].hex()} shim_fdsize={blob[16:20].hex()} payload_base_movz={hex(struct.unpack_from("<I", blob, 33*4)[0])} XNUP_size={size}')
PY
DST=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/device-layer
cp xnu-phk110.img "$DST/" && cp run-payload.bin "$DST/xnu-phk110-payload.bin"
sha256sum "$DST/xnu-phk110.img" "$DST/xnu-phk110-payload.bin"
