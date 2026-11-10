#!/bin/bash
# Wave 23 payload (v19): the virtual-display evidence round -- cmdline-only. Every entry is
# the v18 payload's bytes byte for byte, except cmdline = the new v19 bytes (rec_secs/rec_ring/
# rec_mb + loader_return_after=300; en0_addr traded away for the 607 composed cap -- the T1
# finding in make-cmdline-v19.py). The loader is NOT rebuilt: v18's 553289a4 (pump-forward +
# self-present, PAYLOAD_BASE pinned) is carried over untouched.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v23
mkdir -p $TMP

echo "-- new cmdline v19:"
python3 $R/wave23-scripts/make-cmdline-v19.py "$R/device-layer/udon-hakios-cmdline-v17.bin" \
  "$R/device-layer/udon-hakios-cmdline-v19.bin"

echo "-- extract the v18 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v18.bin" <<'EOF'
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
    open('/tmp/v23/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- assert every carried entry is the v18 bytes (v18 payload vs its own entries):"
python3 - "$R/device-layer/udon-hakios-payload-v18.bin" <<'EOF'
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

v18 = entries(sys.argv[1])
for name in ('loader.efi', 'kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    carried = open('/tmp/v23/' + name, 'rb').read()
    assert carried == v18[name], f'{name} drifted'
lh = hashlib.sha256(v18['loader.efi']).hexdigest()
assert lh.startswith('553289a4'), f'loader.efi is not the v18 build: {lh[:16]}'
kh = hashlib.sha256(v18['kernel']).hexdigest()
assert kh.startswith('17c905ec'), f'kernel is not the v15/v16 build: {kh[:16]}'
print('loader.efi', lh[:16], '(v18, NOT rebuilt)', '| kernel', kh[:16], '(v15/v16)')
EOF

echo "-- v19 payload build (only cmdline differs):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v19.bin" \
  --usb \
  loader.efi=/tmp/v23/loader.efi \
  kernel=/tmp/v23/kernel \
  resident=/tmp/v23/resident \
  ramdisk=/tmp/v23/ramdisk \
  cmdline=$R/device-layer/udon-hakios-cmdline-v19.bin \
  kernel.ver=/tmp/v23/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v19.bin" "$R/device-layer/udon-hakios-payload-v18.bin" <<'EOF'
import struct, sys

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

v19 = entries(sys.argv[1])
v18 = entries(sys.argv[2])
assert sorted(v19) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v19)
assert v19['usb'] == b'1\x00', v19['usb']
for name in ('kernel', 'kernel.ver', 'loader.efi', 'resident', 'ramdisk'):
    assert v19[name] == v18[name], f'{name} drifted from the v18 entry'
assert v19['cmdline'] != v18['cmdline'], 'cmdline must be the NEW v19 bytes'
cmd = v19['cmdline'].rstrip(b'\0').decode()
assert 'rec_secs=280 rec_ring=1 rec_mb=256' in cmd
assert 'loader_return_after=300' in cmd and 'en0_addr' not in cmd
assert len(cmd) == 488, f'cmdline length {len(cmd)} != 488'
print('entries:', sorted(v19))
print('kernel/kernel.ver/loader.efi/resident/ramdisk/usb == v18 entries byte-for-byte; cmdline is the v19 bytes')
assert sum(len(v) for v in v19.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v19:"
sha256sum "$R/device-layer/udon-hakios-payload-v19.bin"
ls -la "$R/device-layer/udon-hakios-payload-v19.bin"
