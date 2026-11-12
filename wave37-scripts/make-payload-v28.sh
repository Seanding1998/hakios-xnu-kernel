#!/bin/bash
# Wave 37 (v28): the v27 payload with the cape-gcc kernel.
# v28 = v27 + kernel swap ONLY: kernel a39c931c -> the wave37 cape-gcc build (printed below);
# cmdline stays the v27 probe cmdline (492 B: gpu=1 + adreno_only=1 inside the string) so the
# next generation runs step 1 alone with per-access prints -- confirming the gcc fix and
# capturing the five register values. ramdisk/loader/resident/kernel.ver/usb = v26/v27 bytes.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v28
mkdir -p $TMP

echo "-- extract the v27 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v27.bin" <<'EOF'
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
    open('/tmp/v28/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel:"
cp $K/hakios-kernel $TMP/kernel
python3 - "$R/wave37-scripts/cmdline-v27.bin" <<'EOF'
import hashlib, sys
k = open('/tmp/v28/kernel','rb').read()
c = open('/tmp/v28/cmdline','rb').read()
c27 = open(sys.argv[1],'rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('a39c931c'), 'kernel did not change'
assert c == c27 and c.endswith(b'adreno_only=1\0'), 'cmdline must stay the v27 probe cmdline'
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 492 B (unchanged probe)')
EOF

echo "-- v28 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v28.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v28.bin" "$R/device-layer/udon-hakios-payload-v27.bin" <<'EOF'
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

v28 = entries(sys.argv[1])
v27 = entries(sys.argv[2])
assert sorted(v28) == sorted(v27) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb', 'cmdline'):
    assert v28[name] == v27[name], f'{name} drifted from the v27 payload entry'
assert v28['kernel'] != v27['kernel'], 'kernel entry must differ (the cape-gcc build)'
assert hashlib.sha256(v28['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v28.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v28['kernel']).hexdigest()[:16]} (was a39c931c...); all else byte-equal v27")
EOF

echo "-- payload v28:"
sha256sum "$R/device-layer/udon-hakios-payload-v28.bin"
