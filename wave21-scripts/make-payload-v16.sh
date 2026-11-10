#!/bin/bash
# Wave 21.1 v16 payload: the delayed-first-try loader (usb_init_kick + 5 s settle + 20 s tempo,
# failed tries now log their start_ex status) + the v16 cmdline (loader_return_after=180, the
# F6 vnode-cliff bypass). The kernel is UNCHANGED from v15 (17c905ec, en0 driver already in) --
# the en0 driver lives in the kernel and the kernel did not move. resident/ramdisk stay pinned
# to the v14/v15 entries byte for byte; the `usb` entry stays.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v16
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v15.bin" <<'EOF'
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
        open('/tmp/v16/' + name, 'wb').write(entry)
        print('carried over:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15's 17c905ec):"
sha256sum /tmp/v16/kernel
sha256sum /tmp/v16/kernel.ver
echo "-- new loader.efi (delayed first try, must NOT be v15.3's 0f7f4028-era bytes):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v16/loader.efi
python3 - <<'EOF'
import hashlib
k = open('/tmp/v16/kernel','rb').read()
h = hashlib.sha256(k).hexdigest()
assert h.startswith('17c905ec'), f'kernel drifted from v15: {h[:16]}'
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel"):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v16/loader.efi','rb').read()
lh = hashlib.sha256(l).hexdigest()
assert not lh.startswith('0f7f4028'), 'loader.efi is still the v15.3 bytes'
for s in (b'oem netmode', b'oem netstat', b'five quiet seconds', b'try failed: start_ex %x', b'D22AP'):
    assert s in l, 'loader missing %s' % s
print('kernel OK:', h[:16], '(byte-identical to v15: en0 driver already in)')
print('loader OK:', lh[:16], '(delayed first try + status prints)')
EOF
echo "-- v16 payload build:"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v16.bin" \
  --usb \
  loader.efi=/tmp/v16/loader.efi \
  kernel=/tmp/v16/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v16.bin \
  kernel.ver=/tmp/v16/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v16.bin" "$R/device-layer/udon-hakios-payload-v15.bin" <<'EOF'
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

v16 = entries(sys.argv[1])
v15 = entries(sys.argv[2])
names = sorted(v16)
assert names == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], names
assert v16['usb'] == b'1\x00', v16['usb']
assert v16['kernel'] == v15['kernel'], 'kernel drifted from the v15 entry'
assert v16['kernel.ver'] == v15['kernel.ver'], 'kernel.ver drifted'
assert v16['loader.efi'] != v15['loader.efi'], 'loader is the v15 bytes'
assert v16['cmdline'] != v15['cmdline'], 'cmdline is the v15 bytes'
assert v16['resident'] == v15['resident'], 'resident drifted from the v15 entry'
assert v16['ramdisk'] == v15['ramdisk'], 'ramdisk drifted from the v15 entry'
print('entries:', sorted(v16))
print('kernel/kernel.ver/resident/ramdisk == v15 entries byte-for-byte; loader/cmdline are the new v16 bytes')
assert sum(len(v) for v in v16.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v16:"
sha256sum "$R/device-layer/udon-hakios-payload-v16.bin"
ls -la "$R/device-layer/udon-hakios-payload-v16.bin"
