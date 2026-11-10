#!/bin/bash
# Wave 21.2 v16c payload: v16b' (boot-window-only bring-up + PAYLOAD_BASE=0xF4000000) plus the
# DWC3 wake (SUSPHY off + GCTL.CSFTRST core soft reset before the bring-up -- the warm-boot
# endpoint-wall cure). Kernel/cmdline/resident/ramdisk stay pinned byte for byte.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v16c
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v16b.bin" <<'EOF'
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
        open('/tmp/v16c/' + name, 'wb').write(entry)
        print('carried over:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15/v16's 17c905ec):"
sha256sum /tmp/v16c/kernel
sha256sum /tmp/v16c/kernel.ver
echo "-- new loader.efi (DWC3 wake, must NOT be v16b's 6c7fdb62 / broken f445f187 bytes):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v16c/loader.efi
python3 - <<'EOF'
import hashlib, struct
k = open('/tmp/v16c/kernel','rb').read()
h = hashlib.sha256(k).hexdigest()
assert h.startswith('17c905ec'), f'kernel drifted from v15/v16: {h[:16]}'
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel"):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v16c/loader.efi','rb').read()
lh = hashlib.sha256(l).hexdigest()
assert not lh.startswith('6c7fdb62'), 'loader.efi is still the v16b bytes'
assert not lh.startswith('f445f187'), 'loader.efi is the broken 0xF0000000-based v16b bytes'
assert not lh.startswith('d612958d'), 'loader.efi is still the v16 bytes'
for s in (b'oem netmode', b'oem netstat', b'twenty-five quiet seconds',
          b'usb: warm-boot start failed after %d tries', b'try failed: start_ex %x', b'D22AP',
          b'usb: dwc3 woken (phy suspend off + core soft reset)'):
    assert s in l, 'loader missing %s' % s
# F10 pin (layout-robust): find the XNUP movk (0x72AA0AB3), the word 8 bytes later must be
# movz w8, #0xF4000000 (0x52BE8008) -- the bare-build redwood default (0xF0000000) fails this.
needle = struct.pack('<I', 0x72AA0AB3)
i = l.find(needle)
assert i >= 0, 'XNUP movk not found in loader'
w = struct.unpack_from('<I', l, i + 8)[0]
assert w == 0x52BE8008, f'PAYLOAD_BASE pin failed: {w:#x}'
print('kernel OK:', h[:16], '(byte-identical to v15/v16)')
print('loader OK:', lh[:16], '(DWC3 wake + PAYLOAD_BASE=0xF4000000 pinned)')
EOF
echo "-- v16c payload build:"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v16c.bin" \
  --usb \
  loader.efi=/tmp/v16c/loader.efi \
  kernel=/tmp/v16c/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v16b.bin \
  kernel.ver=/tmp/v16c/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v16c.bin" "$R/device-layer/udon-hakios-payload-v16b.bin" <<'EOF'
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

v16c = entries(sys.argv[1])
v16b = entries(sys.argv[2])
names = sorted(v16c)
assert names == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], names
assert v16c['usb'] == b'1\x00', v16c['usb']
assert v16c['kernel'] == v16b['kernel'], 'kernel drifted'
assert v16c['kernel.ver'] == v16b['kernel.ver'], 'kernel.ver drifted'
assert v16c['loader.efi'] != v16b['loader.efi'], 'loader is the v16b bytes'
assert v16c['cmdline'] == v16b['cmdline'], 'cmdline must stay the v16 bytes byte-for-byte'
assert v16c['resident'] == v16b['resident'], 'resident drifted'
assert v16c['ramdisk'] == v16b['ramdisk'], 'ramdisk drifted'
print('entries:', sorted(v16c))
print('kernel/kernel.ver/resident/ramdisk/cmdline == v16b entries byte-for-byte; loader.efi is the new v16c bytes')
assert sum(len(v) for v in v16c.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v16c:"
sha256sum "$R/device-layer/udon-hakios-payload-v16c.bin"
ls -la "$R/device-layer/udon-hakios-payload-v16c.bin"
