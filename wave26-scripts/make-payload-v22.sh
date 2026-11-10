#!/bin/bash
# Wave 26 Round 2 (v22) payload: the v21 payload with only the loader swapped for the
# maxvnodes build (the DT /defaults injection of kern.maxvnodes=8192 -- the vnode cap
# (CONFIG_VNODES=1024) is what wedged every session at ~220 s). kernel/cmdline/resident/
# ramdisk/kernel.ver/usb are the v21 payload's entries byte for byte.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v22
mkdir -p $TMP

echo "-- extract the v21 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v21.bin" <<'EOF'
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
    open('/tmp/v22/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- v22 payload build (loader swapped for the maxvnodes build, all else pinned to v21):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v22.bin" \
  --usb \
  loader.efi=$HOME/hakios/kernel/xnuloader/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v22.bin" "$R/device-layer/udon-hakios-payload-v21.bin" <<'EOF'
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

v22 = entries(sys.argv[1])
v21 = entries(sys.argv[2])
assert sorted(v22) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v22)
for name in ('kernel', 'kernel.ver', 'cmdline', 'resident', 'ramdisk', 'usb'):
    assert v22[name] == v21[name], f'{name} drifted from the v21 payload entry'
l = v22['loader.efi']
lh = hashlib.sha256(l).hexdigest()
assert l != v21['loader.efi'], 'loader is not the maxvnodes build'
assert hashlib.sha256(v21['loader.efi']).hexdigest().startswith('b8a2150b'), 'the v21 loader pin moved'
assert lh.startswith('0ade78b5'), f'loader.efi is not the Wave 26 maxvnodes build: {lh[:16]}'
assert b'kern.maxvnodes' in l, 'the maxvnodes DT property name is not in the loader'
for s in (b'checkpoint-1: the standing receive is in',
          b'checkpoint-3: the standing receive finished',
          b'the console mirror: vendor door',
          b'soft reset was still set after the wait: cleared by hand',
          b'the bring-up begins (the Wave 24 timeline runs from here)',
          b'the re-throw did not come back',
          b'kept its host: no re-throw'):
    assert s in l, f'loader missing Wave 24 mechanism {s}'
import struct as st
found = None
for m in range(0, len(l) - 40, 4):
    if st.unpack_from('<I', l, m)[0] == 0x52BE8008:      # movz w?, #0xF400, lsl #16
        for kk in (1, 2, 3, 4, 5, 6):
            if st.unpack_from('<I', l, m + 4 * kk)[0] == 0x72AA0AB3:   # movk w?, #0x5055, lsl #16
                found = (m, kk)
                break
        if found:
            break
assert found, 'PAYLOAD_BASE pin missing'
off = struct.unpack_from('<I', l, 0x3C)[0]
epi = struct.unpack_from('<I', l, off + 24 + 16)[0]
assert epi == 0x2140, f'entry RVA moved: {hex(epi)}'
print(f"loader.efi {lh[:16]} (Wave 26 maxvnodes build; PAYLOAD_BASE pin at {hex(found[0])}, entry RVA 0x2140)")
print(f"kernel {hashlib.sha256(v22['kernel']).hexdigest()[:16]} == v21's byte for byte")
print('kernel/cmdline/resident/ramdisk/kernel.ver/usb == v21 payload entries byte-for-byte')
assert sum(len(v) for v in v22.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v22:"
sha256sum "$R/device-layer/udon-hakios-payload-v22.bin"
