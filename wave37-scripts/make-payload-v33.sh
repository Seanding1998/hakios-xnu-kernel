#!/bin/bash
# Wave 37 (v33): the v32 payload with the gen7-native-step-20 kernel.
# v33 = v32 + kernel swap ONLY (ee283c74 -> 55a8d40f: the a6xx twelve-register address-mode list
# out of step 20 -- the sixth of them reset the phone in the v32 walk; the vendor gen7 driver
# writes none of them). cmdline stays the v26 bytes (gpu=1 alone).
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v33
mkdir -p $TMP

echo "-- extract the v32 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v32.bin" <<'EOF'
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
    open('/tmp/v33/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel:"
cp $K/hakios-kernel $TMP/kernel
python3 - <<'EOF'
import hashlib
k = open('/tmp/v33/kernel','rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('ee283c74'), 'kernel did not change'
c = open('/tmp/v33/cmdline','rb').read()
assert c.endswith(b'gpu=1\0') and len(c) == 478, 'cmdline must stay the v26 bytes'
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 478 B (unchanged production)')
EOF

echo "-- v33 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v33.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v33.bin" "$R/device-layer/udon-hakios-payload-v32.bin" <<'EOF'
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

v33 = entries(sys.argv[1])
v32 = entries(sys.argv[2])
assert sorted(v33) == sorted(v32) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb', 'cmdline'):
    assert v33[name] == v32[name], f'{name} drifted from the v32 payload entry'
assert v33['kernel'] != v32['kernel'], 'kernel entry must differ'
assert hashlib.sha256(v33['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v33.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v33['kernel']).hexdigest()[:16]} (was ee283c74...); all else byte-equal v32")
EOF

echo "-- payload v33:"
sha256sum "$R/device-layer/udon-hakios-payload-v33.bin"
