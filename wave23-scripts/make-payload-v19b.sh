#!/bin/bash
# Wave 23 Round 2 payload (v19b): the v19 payload with the loader swapped for the patched
# v19b build (9dc2f5db: softened re-throw + service-early + raw-code + settle-5s, the
# coordinator's four items). Kernel/cmdline/resident/ramdisk/kernel.ver/usb are the v19
# payload's entries byte for byte (cmdline stays the v19 bytes -- the recording round).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v23
mkdir -p $TMP

echo "-- extract the v19 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v19.bin" <<'EOF'
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

echo "-- v19b payload build (loader swapped, all else pinned):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v19b.bin" \
  --usb \
  loader.efi=$HOME/hakios/kernel/xnuloader/loader.efi \
  kernel=/tmp/v23/kernel \
  resident=/tmp/v23/resident \
  ramdisk=/tmp/v23/ramdisk \
  cmdline=$R/device-layer/udon-hakios-cmdline-v19.bin \
  kernel.ver=/tmp/v23/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v19b.bin" "$R/device-layer/udon-hakios-payload-v19.bin" <<'EOF'
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

v19b = entries(sys.argv[1])
v19 = entries(sys.argv[2])
assert sorted(v19b) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v19b)
for name in ('kernel', 'kernel.ver', 'cmdline', 'resident', 'ramdisk', 'usb'):
    assert v19b[name] == v19[name], f'{name} drifted from the v19 entry'
lh = hashlib.sha256(v19b['loader.efi']).hexdigest()
assert lh.startswith('9dc2f5db'), f'loader.efi is not the v19b build: {lh[:16]}'
l = v19b['loader.efi']
for s in (b'five quiet seconds before the first try',
          b'the re-throw is softened',
          b'kept its host: no re-throw',
          b'through UsbFn (raw)',
          b'the bring-up is still arming',
          b'a host is out there (a device state change'):
    assert s in l, f'v19b loader missing {s}'
assert b'twenty-five quiet seconds before the first try' not in l
import struct as st
m = l.find(st.pack('<I', 0x72AA0AB3))
assert m >= 0 and st.unpack_from('<I', l, m + 8)[0] == 0x52BE8008, 'PAYLOAD_BASE pin failed'
print('loader.efi', lh[:16], '(v19b: softened re-throw + serve-early + raw code + settle 5s)')
print('kernel/cmdline/resident/ramdisk/kernel.ver/usb == v19 entries byte-for-byte')
assert sum(len(v) for v in v19b.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v19b:"
sha256sum "$R/device-layer/udon-hakios-payload-v19b.bin"
ls -la "$R/device-layer/udon-hakios-payload-v19b.bin"
