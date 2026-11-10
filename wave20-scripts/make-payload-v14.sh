#!/bin/bash
# Wave 20 v14 payload: the hw_target kernel (883e99e7, first kernel change since
# v11) + the REAL-IDENTITY loader (7ba818d2, rebuilt from the d22ap device tree:
# the placeholder identity was why hw.target answered EINVAL) + the v14 cmdline
# + the fresh FLASHBOOT=1 CRYPTEXES=flash images.
# kernel.ver stays byte-pinned to the v13 entry (extract of the v11 hand-off).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v14
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v13.bin" <<'EOF'
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
    if name == 'kernel.ver':
        open('/tmp/v14/kernel.ver', 'wb').write(entry)
EOF
echo "-- pinned kernel.ver (must be the v11 hand-off afd473f5):"
sha256sum /tmp/v14/kernel.ver
echo "-- new kernel (hw_target fix, must NOT be a7f4641f):"
sha256sum $K/hakios-kernel
cp $K/hakios-kernel /tmp/v14/kernel
echo "-- new loader.efi (real identity, must NOT be 66c6b342, carries D22AP):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v14/loader.efi
python3 - <<'EOF'
import hashlib
h = hashlib.sha256(open('/tmp/v14/kernel','rb').read()).hexdigest()
assert h.startswith('883e99e7'), h
l = open('/tmp/v14/loader.efi','rb').read()
assert hashlib.sha256(l).hexdigest().startswith('7ba818d2'), 'loader.efi not the real-identity build'
assert b'D22AP' in l and b'RAMDisk1' in l and b'may be written this run' in l, 'loader missing identity or dual-ramdisk support'
print('kernel sha OK:', h[:16])
print('loader sha OK: 7ba818d2 (real identity + dual ramdisk)')
EOF
echo "-- v14 images:"
sha256sum $K/userland/flashboot.apfs $K/userland/root.apfs
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v14.bin" \
  loader.efi=/tmp/v14/loader.efi \
  kernel=/tmp/v14/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v14.bin \
  kernel.ver=/tmp/v14/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v14.bin" <<'EOF'
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
assert size <= 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v14:"
sha256sum "$R/device-layer/udon-hakios-payload-v14.bin"
ls -la "$R/device-layer/udon-hakios-payload-v14.bin"
