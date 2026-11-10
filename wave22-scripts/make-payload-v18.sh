#!/bin/bash
# Wave 22 payload (v18): the host-visibility round -- pump-forward (every post-start_ex wait
# pumps at a 20 ms tick cadence) + self-presentation (the loader raises the pull-up itself
# after every successful start_ex, the vendor connect's own final write, in a pumped window).
# Kernel/cmdline/resident/ramdisk pinned to the v16 entries byte for byte.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v18
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
        open('/tmp/v18/' + name, 'wb').write(entry)
        print('carried over:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15/v16's 17c905ec):"
sha256sum /tmp/v18/kernel
sha256sum /tmp/v18/kernel.ver
echo "-- new loader.efi (host visibility: pump-forward + self-present; must be none of the retired builds):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v18/loader.efi
python3 - <<'EOF'
import hashlib, struct
k = open('/tmp/v18/kernel','rb').read()
h = hashlib.sha256(k).hexdigest()
assert h.startswith('17c905ec'), f'kernel drifted from v15/v16: {h[:16]}'
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel"):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v18/loader.efi','rb').read()
lh = hashlib.sha256(l).hexdigest()
for retired in ('d612958d', '6c7fdb62', 'f445f187', '45437cd3', '47acf7b0', 'd368c8aa'):
    assert not lh.startswith(retired), f'loader.efi is a retired build ({retired})'
assert lh.startswith('553289a4'), f'unexpected loader build: {lh[:16]}'
for s in (b'oem netmode', b'oem netstat', b'twenty-five quiet seconds',
          b'usb: warm-boot start failed after %d tries', b'try failed: start_ex %x', b'D22AP',
          b'usb: dwc3 woken (phy suspend off + core soft reset)',
          b'usb: bulk probe gen %d beat %d: %x',
          b'usb: the bulk pair answered: armed at generation %d, beat %d',
          b'the pair never armed across 3 generations',
          b'the pair is un-armed after generation %d (last %x)',
          b"twenty-five quiet seconds before the re-throw's try",
          b'the re-throw did not come back',
          # Wave 22's own strings:
          b'the gadget is presented to the host (the pull-up is ours)'):
    assert s in l, 'loader missing %s' % s
for gone in (b'a non-wall probe answer stopped the stage',
             b'the wall stands after 3 generations',
             b'the wall stands after generation',
             b'stopped the stage'):
    assert gone not in l, f'loader still carries the v17 string: {gone.decode()}'
assert l.count(b'USB->stop') == 0, 'loader still calls USB->stop'
assert b'asked up; five quiet seconds' not in l, 'loader still carries the v16 settle line'
assert b'started late' not in l, 'loader still carries the retired lazy-retry line'
# F10 lesson (Boot #31): pin the payload base -- the XNUP-magic movk must be followed by
# movz w8, #0xF4000000 (0x52BE8008); the bare-build redwood default fails this.
m = l.find(struct.pack('<I', 0x72AA0AB3))
assert m >= 0, 'XNUP movk not found'
assert struct.unpack_from('<I', l, m + 8)[0] == 0x52BE8008, \
    "loader was built WITHOUT PAYLOAD_BASE=0xF4000000 (redwood 0xF0000000 default -- Boot #31 freeze)"
print('kernel OK:', h[:16], '(byte-identical to v15/v16: en0 driver already in)')
print('loader OK:', lh[:16], '(pump-forward + self-present + PAYLOAD_BASE pinned)')
EOF
echo "-- v18 payload build:"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v18.bin" \
  --usb \
  loader.efi=/tmp/v18/loader.efi \
  kernel=/tmp/v18/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v17.bin \
  kernel.ver=/tmp/v18/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v18.bin" "$R/device-layer/udon-hakios-payload-v16.bin" <<'EOF'
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

v18 = entries(sys.argv[1])
v16 = entries(sys.argv[2])
assert sorted(v18) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v18)
assert v18['usb'] == b'1\x00', v18['usb']
assert v18['kernel'] == v16['kernel'], 'kernel drifted from the v16 entry'
assert v18['kernel.ver'] == v16['kernel.ver'], 'kernel.ver drifted'
assert v18['loader.efi'] != v16['loader.efi'], 'loader is the v16 bytes'
assert v18['cmdline'] == v16['cmdline'], 'cmdline must be the v16 bytes byte-for-byte'
assert v18['resident'] == v16['resident'], 'resident drifted from the v16 entry'
assert v18['ramdisk'] == v16['ramdisk'], 'ramdisk drifted from the v16 entry'
print('entries:', sorted(v18))
print('kernel/kernel.ver/resident/ramdisk/cmdline == v16 entries byte-for-byte; loader.efi is the new v18 bytes')
assert sum(len(v) for v in v18.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v18:"
sha256sum "$R/device-layer/udon-hakios-payload-v18.bin"
ls -la "$R/device-layer/udon-hakios-payload-v18.bin"
