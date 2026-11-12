#!/bin/bash
# Wave 37 (v31): the production attempt.
# v31 = v30 + kernel swap (95fd7568 -> a696adb0: the cb write out of step 5, cape-native) +
# cmdline swap back to the v26 bytes (477 chars + NUL: gpu=1 alone -- the full machine to step 21,
# skipping 10-12, pauses off, keep=1: "THE GPU STAYS ON" if everything answers). Budget 587/607.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v31
mkdir -p $TMP

echo "-- extract the v30 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v30.bin" <<'EOF'
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
    open('/tmp/v31/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel + the production cmdline:"
cp $K/hakios-kernel $TMP/kernel
python3 - "$R/wave36-scripts/cmdline-v26.bin" <<'EOF'
import hashlib, sys
k = open('/tmp/v31/kernel','rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('95fd7568'), 'kernel did not change'
c26 = open(sys.argv[1],'rb').read()
assert c26.endswith(b'gpu=1\0') and c26.count(b'\0') == 1 and len(c26) == 478, 'v26 cmdline not as expected'
open('/tmp/v31/cmdline','wb').write(c26)
open('/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave37-scripts/cmdline-v31.bin','wb').write(c26)
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 478 B (v26 bytes: gpu=1 alone)')
EOF

echo "-- v31 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v31.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v31.bin" "$R/device-layer/udon-hakios-payload-v30.bin" <<'EOF'
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

v31 = entries(sys.argv[1])
v30 = entries(sys.argv[2])
assert sorted(v31) == sorted(v30) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v31[name] == v30[name], f'{name} drifted from the v30 payload entry'
assert v31['kernel'] != v30['kernel'] and v31['cmdline'] != v30['cmdline']
assert hashlib.sha256(v31['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v31.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v31['kernel']).hexdigest()[:16]} (was 95fd7568...); cmdline = v26 bytes; all else byte-equal v30")
EOF

echo "-- payload v31:"
sha256sum "$R/device-layer/udon-hakios-payload-v31.bin"
