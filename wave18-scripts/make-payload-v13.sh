#!/bin/bash
# Wave 18 v13 payload (fixed): kernel.ver goes in as a plain item, so every
# entry precedes the terminator. loader.efi/kernel/kernel.ver byte-pinned.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v13
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v11.bin" <<'EOF'
import struct, sys
data = open(sys.argv[1], 'rb').read()
magic, size = struct.unpack_from('<II', data, 0)
off = 8
while off < 8 + size:
    name, esize, _ = struct.unpack_from('<16sII', data, off)
    name = name.rstrip(b'\0').decode()
    off += 24
    if name == '':
        break
    entry = data[off:off + esize]
    off += esize + (-esize % 16)
    if name == 'loader.efi':
        open('/tmp/v13/loader.efi', 'wb').write(entry)
    if name == 'kernel.ver':
        open('/tmp/v13/kernel.ver', 'wb').write(entry)
EOF
sha256sum /tmp/v13/loader.efi /tmp/v13/kernel.ver
cp $K/hakios-kernel /tmp/v13/kernel
python3 - <<'EOF'
import hashlib
h = hashlib.sha256(open('/tmp/v13/kernel','rb').read()).hexdigest()
assert h.startswith('a7f4641f'), h
print('kernel sha OK:', h[:16])
EOF
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v13.bin" \
  loader.efi=/tmp/v13/loader.efi \
  kernel=/tmp/v13/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v13.bin \
  kernel.ver=/tmp/v13/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v13.bin" <<'EOF'
import struct, sys
data = open(sys.argv[1], 'rb').read()
magic, size = struct.unpack_from('<II', data, 0)
off = 8
names = []
while off < 8 + size:
    name, esize, _ = struct.unpack_from('<16sII', data, off)
    name = name.rstrip(b'\0').decode()
    off += 24
    if name == '':
        break
    names.append(name)
    off += esize + (-esize % 16)
assert off == 8 + size, 'trailing bytes'
print('entries:', names)
assert names == ['loader.efi', 'kernel', 'resident', 'ramdisk', 'cmdline', 'kernel.ver'], names
EOF
sha256sum "$R/device-layer/udon-hakios-payload-v13.bin"
