#!/bin/bash
# Wave 21.5 v17 payload: the bulk pair's arm probe + the wall re-throw (the loader verifies
# its own arm after start_ex and re-throws the bring-up on the 0x8000000C wall) over the
# v16 cmdline bytes (unchanged: loader_return_after=180, en0_addr=10.0.0.2). The kernel is
# UNCHANGED from v15/v16 (17c905ec, en0 driver already in); resident/ramdisk stay pinned to
# the v16 entries byte for byte; the `usb` entry stays; the loader carries the v16b
# boot-window bring-up and the v16c DWC3 wake underneath the new stage.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v17
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
        open('/tmp/v17/' + name, 'wb').write(entry)
        print('carried over:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15/v16's 17c905ec):"
sha256sum /tmp/v17/kernel
sha256sum /tmp/v17/kernel.ver
echo "-- new loader.efi (arm probe + re-throw, must be none of the retired builds):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v17/loader.efi
python3 - <<'EOF'
import hashlib, struct
k = open('/tmp/v17/kernel','rb').read()
h = hashlib.sha256(k).hexdigest()
assert h.startswith('17c905ec'), f'kernel drifted from v15/v16: {h[:16]}'
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel"):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v17/loader.efi','rb').read()
lh = hashlib.sha256(l).hexdigest()
assert not lh.startswith('d612958d'), 'loader.efi is still the v16 bytes'
assert not lh.startswith('6c7fdb62'), 'loader.efi is still the v16b bytes'
assert not lh.startswith('f445f187'), 'loader.efi is the 0xF0000000-based broken v16b bytes'
assert not lh.startswith('45437cd3'), 'loader.efi is still the v16c bytes'
assert lh.startswith('47acf7b0'), f'unexpected loader build: {lh[:16]}'
for s in (b'oem netmode', b'oem netstat', b'twenty-five quiet seconds',
          b'usb: warm-boot start failed after %d tries', b'try failed: start_ex %x', b'D22AP',
          b'usb: dwc3 woken (phy suspend off + core soft reset)',
          b'usb: bulk probe gen %d beat %d: %x',
          b'usb: the bulk pair answered: armed at generation %d, beat %d',
          b'a non-wall probe answer stopped the stage',
          b'the wall stands after 3 generations',
          b"twenty-five quiet seconds before the re-throw's try",
          b'the re-throw did not come back'):
    assert s in l, 'loader missing %s' % s
assert b'asked up; five quiet seconds' not in l, 'loader still carries the v16 settle line'
assert b'started late' not in l, 'loader still carries the retired lazy-retry line'
# F10 lesson: the payload base is a compile-time -DPAYLOAD_BASE. The bare `./build.sh` default is
# redwood's 0xF0000000, which is unmapped on udon -- parse_payload's first `ph->magic` read faults
# (Boot #31's freeze). Pin the entry's constant: right after the XNUP-magic movk the loader must
# hold movz w8, #0xF4000000 (word 0x52BE8008). (Layout-robust: searched, not address-pinned.)
m = l.find(struct.pack('<I', 0x72AA0AB3))
assert m >= 0, 'XNUP movk not found'
assert struct.unpack_from('<I', l, m + 8)[0] == 0x52BE8008, \
    "loader was built WITHOUT PAYLOAD_BASE=0xF4000000 (redwood 0xF0000000 default -- Boot #31 freeze)"
print('kernel OK:', h[:16], '(byte-identical to v15/v16: en0 driver already in)')
print('loader OK:', lh[:16], '(arm probe + re-throw + PAYLOAD_BASE=0xF4000000 pinned)')
EOF
echo "-- v17 payload build:"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v17.bin" \
  --usb \
  loader.efi=/tmp/v17/loader.efi \
  kernel=/tmp/v17/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v17.bin \
  kernel.ver=/tmp/v17/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v17.bin" "$R/device-layer/udon-hakios-payload-v16.bin" <<'EOF'
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

v17 = entries(sys.argv[1])
v16 = entries(sys.argv[2])
names = sorted(v17)
assert names == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], names
assert v17['usb'] == b'1\x00', v17['usb']
assert v17['kernel'] == v16['kernel'], 'kernel drifted from the v16 entry'
assert v17['kernel.ver'] == v16['kernel.ver'], 'kernel.ver drifted'
assert v17['loader.efi'] != v16['loader.efi'], 'loader is the v16 bytes'
assert v17['cmdline'] == v16['cmdline'], 'cmdline must be the v16 bytes byte-for-byte (21.5 moves no boot-arg)'
assert v17['resident'] == v16['resident'], 'resident drifted from the v16 entry'
assert v17['ramdisk'] == v16['ramdisk'], 'ramdisk drifted from the v16 entry'
print('entries:', sorted(v17))
print('kernel/kernel.ver/resident/ramdisk/cmdline == v16 entries byte-for-byte; loader.efi is the new v17 bytes')
assert sum(len(v) for v in v17.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v17:"
sha256sum "$R/device-layer/udon-hakios-payload-v17.bin"
ls -la "$R/device-layer/udon-hakios-payload-v17.bin"
