#!/bin/bash
# Wave 37 (v32): the v31 payload with the cape-zap kernel.
# v32 = v31 + kernel swap ONLY (a696adb0 -> ee283c74: zap_header() reads cape's three-segment
# a730_zap.mdt -- the hashes are segment 2, not segment 1; step-5 announce offsets refreshed).
# cmdline stays the v26 bytes (gpu=1 alone). ramdisk/loader/resident/kernel.ver/usb carried.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v32
mkdir -p $TMP

echo "-- extract the v31 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v31.bin" <<'EOF'
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
    open('/tmp/v32/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel:"
cp $K/hakios-kernel $TMP/kernel
python3 - <<'EOF'
import hashlib
k = open('/tmp/v32/kernel','rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('a696adb0'), 'kernel did not change'
c = open('/tmp/v32/cmdline','rb').read()
assert c.endswith(b'gpu=1\0') and len(c) == 478, 'cmdline must stay the v26 bytes'
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 478 B (unchanged production)')
EOF

echo "-- v32 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v32.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v32.bin" "$R/device-layer/udon-hakios-payload-v31.bin" <<'EOF'
import hashlib, struct, sys

def entries(path):
    data = open(path, 'rb').read()
    magic, size = struct.unpack_from('<II', data, 0)
    assert magic == 0x50554E58, 'not XNUP'
    out = {}
    off = 8
    while off < 8 + size:
        name, esize, _ = struct.unpack_from('<16sII', data, off)
        name = name.rstrip(b'\0').decode()
        off += 24
        if name == '':
            break
        out[name] = data[off:off + esize]
        off += esize + (-esize % 16)
    assert off == 8 + size, 'trailing bytes'
    return out

v32 = entries(sys.argv[1])
v31 = entries(sys.argv[2])
assert sorted(v32) == sorted(v31) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb', 'cmdline'):
    assert v32[name] == v31[name], f'{name} drifted from the v31 payload entry'
assert v32['kernel'] != v31['kernel'], 'kernel entry must differ'
assert hashlib.sha256(v32['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v32.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v32['kernel']).hexdigest()[:16]} (was a696adb0...); all else byte-equal v31")
EOF

echo "-- payload v32:"
sha256sum "$R/device-layer/udon-hakios-payload-v32.bin"
