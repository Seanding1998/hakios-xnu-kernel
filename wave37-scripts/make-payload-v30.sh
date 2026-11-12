#!/bin/bash
# Wave 37 (v30): the v29 payload with the cape-native-step-2 kernel.
# v30 = v29 + kernel swap ONLY (c2ea0ca2 -> 95fd7568: step 2 reads nothing, matching the phone's
# own live device tree and the vendor driver's skip). cmdline stays the v29 walk (487 B:
# gpu=1 adreno=3). ramdisk/loader/resident/kernel.ver/usb = v26..v29 bytes.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v30
mkdir -p $TMP

echo "-- extract the v29 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v29.bin" <<'EOF'
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
    open('/tmp/v30/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel:"
cp $K/hakios-kernel $TMP/kernel
python3 - <<'EOF'
import hashlib
k = open('/tmp/v30/kernel','rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('c2ea0ca2'), 'kernel did not change'
c = open('/tmp/v30/cmdline','rb').read()
assert c.endswith(b'gpu=1 adreno=3\0'), 'cmdline must stay the v29 walk'
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 487 B (unchanged walk)')
EOF

echo "-- v30 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v30.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v30.bin" "$R/device-layer/udon-hakios-payload-v29.bin" <<'EOF'
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

v30 = entries(sys.argv[1])
v29 = entries(sys.argv[2])
assert sorted(v30) == sorted(v29) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb', 'cmdline'):
    assert v30[name] == v29[name], f'{name} drifted from the v29 payload entry'
assert v30['kernel'] != v29['kernel'], 'kernel entry must differ'
assert hashlib.sha256(v30['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v30.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v30['kernel']).hexdigest()[:16]} (was c2ea0ca2...); all else byte-equal v29")
EOF

echo "-- payload v30:"
sha256sum "$R/device-layer/udon-hakios-payload-v30.bin"
