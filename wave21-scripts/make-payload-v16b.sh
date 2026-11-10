#!/bin/bash
# Wave 21.2 v16b payload: the boot-window-only USB bring-up (lazy retry retired + settle 25 s
# + three tries at a 25 s tempo + the give-up line that names the cold boot) over the v16
# cmdline bytes (unchanged: loader_return_after=180, en0_addr=10.0.0.2). The kernel is
# UNCHANGED from v15/v16 (17c905ec, en0 driver already in); resident/ramdisk stay pinned to
# the v16 (= v15) entries byte for byte; the `usb` entry stays.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v16b
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v16.bin" <<'EOF'
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
    if name in ('kernel', 'kernel.ver'):
        open('/tmp/v16b/' + name, 'wb').write(entry)
        print('carried over:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15/v16's 17c905ec):"
sha256sum /tmp/v16b/kernel
sha256sum /tmp/v16b/kernel.ver
echo "-- new loader.efi (boot-window-only bring-up, must NOT be v16's d612958d bytes):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v16b/loader.efi
python3 - <<'EOF'
import hashlib, struct
k = open('/tmp/v16b/kernel','rb').read()
h = hashlib.sha256(k).hexdigest()
assert h.startswith('17c905ec'), f'kernel drifted from v15/v16: {h[:16]}'
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel"):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v16b/loader.efi','rb').read()
lh = hashlib.sha256(l).hexdigest()
assert not lh.startswith('d612958d'), 'loader.efi is still the v16 bytes'
assert not lh.startswith('0f7f4028'), 'loader.efi is still the v15.3 bytes'
assert not lh.startswith('f445f187'), 'loader.efi is still the 0xF0000000-based v16b bytes (missing PAYLOAD_BASE=0xF4000000)'
for s in (b'oem netmode', b'oem netstat', b'twenty-five quiet seconds',
          b'usb: warm-boot start failed after %d tries', b'try failed: start_ex %x', b'D22AP'):
    assert s in l, 'loader missing %s' % s
assert b'asked up; five quiet seconds' not in l, 'loader still carries the v16 settle line'
assert b'started late' not in l, 'loader still carries the retired lazy-retry line'
# F10 lesson: the payload base is a compile-time -DPAYLOAD_BASE. The bare `./build.sh` default is
# redwood's 0xF0000000, which is unmapped on udon -- parse_payload's first `ph->magic` read faults
# (Boot #31's freeze). Pin the entry's constant: at RVA 0x2198 the loader must hold
# movz w8, #0xF4000000 (word 0x52BE8008) right after the XNUP-magic movk at 0x2190.
off = struct.unpack_from('<I', l, 0x3C)[0]
ep = struct.unpack_from('<I', l, off + 24 + 16)[0]
assert ep == 0x2140, hex(ep)
sect = off + 24 + struct.unpack_from('<H', l, off + 20)[0]
nsec = struct.unpack_from('<H', l, off + 6)[0]
va = praw = None
for i in range(nsec):
    s = l[sect + 40*i: sect + 40*i + 40]
    if s[:5] == b'.text':
        _vs, va, _rs, praw = struct.unpack_from('<IIII', s[8:24])
        break
def rva2off(r):
    return r - va + praw
assert struct.unpack_from('<I', l, rva2off(0x2190))[0] == 0x72AA0AB3, 'XNUP movk moved'
assert struct.unpack_from('<I', l, rva2off(0x2198))[0] == 0x52BE8008, \
    "loader was built WITHOUT PAYLOAD_BASE=0xF4000000 (redwood 0xF0000000 default -- Boot #31 freeze)"
print('kernel OK:', h[:16], '(byte-identical to v15/v16: en0 driver already in)')
print('loader OK:', lh[:16], '(boot-window-only bring-up + PAYLOAD_BASE=0xF4000000 pinned)')
EOF
echo "-- v16b payload build:"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v16b.bin" \
  --usb \
  loader.efi=/tmp/v16b/loader.efi \
  kernel=/tmp/v16b/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v16b.bin \
  kernel.ver=/tmp/v16b/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v16b.bin" "$R/device-layer/udon-hakios-payload-v16.bin" <<'EOF'
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

v16b = entries(sys.argv[1])
v16 = entries(sys.argv[2])
names = sorted(v16b)
assert names == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], names
assert v16b['usb'] == b'1\x00', v16b['usb']
assert v16b['kernel'] == v16['kernel'], 'kernel drifted from the v16 entry'
assert v16b['kernel.ver'] == v16['kernel.ver'], 'kernel.ver drifted'
assert v16b['loader.efi'] != v16['loader.efi'], 'loader is the v16 bytes'
assert v16b['cmdline'] == v16['cmdline'], 'cmdline must be the v16 bytes byte-for-byte (21.2 moves no boot-arg)'
assert v16b['resident'] == v16['resident'], 'resident drifted from the v16 entry'
assert v16b['ramdisk'] == v16['ramdisk'], 'ramdisk drifted from the v16 entry'
print('entries:', sorted(v16b))
print('kernel/kernel.ver/resident/ramdisk/cmdline == v16 entries byte-for-byte; loader.efi is the new v16b bytes')
assert sum(len(v) for v in v16b.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v16b:"
sha256sum "$R/device-layer/udon-hakios-payload-v16b.bin"
ls -la "$R/device-layer/udon-hakios-payload-v16b.bin"
