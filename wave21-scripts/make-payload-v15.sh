#!/bin/bash
# Wave 21 v15 payload: the en0-over-loader kernel (first change since v14's hw_target) + the
# net-ring loader (BLOCK_VERSION 4, netmode/netstat, usb-first flow) + the v15 cmdline + the
# wave18/20 userland images, byte-identical. NEW: the payload carries the `usb` entry, so the
# loader's USB command server is up before the kernel runs and stays for the session (that is
# the whole data plane: netmode, logdump, and every N1-N3 tool talk to it).
# kernel.ver stays byte-pinned to the v13/v14 entry (extract of the v11 hand-off).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=~/hakios/kernel
TMP=/tmp/v15
mkdir -p $TMP
cd $K
python3 - "$R/device-layer/udon-hakios-payload-v14.bin" <<'EOF'
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
    if name == 'kernel.ver':
        open('/tmp/v15/kernel.ver', 'wb').write(entry)
EOF
echo "-- pinned kernel.ver (must be the v11 hand-off afd473f5):"
sha256sum /tmp/v15/kernel.ver
echo "-- new kernel (en0 over the loader, must NOT be 883e99e7):"
sha256sum $K/hakios-kernel
cp $K/hakios-kernel /tmp/v15/kernel
echo "-- new loader.efi (net ring, must NOT be 7ba818d2, carries the netmode strings):"
sha256sum $K/xnuloader/loader.efi
cp $K/xnuloader/loader.efi /tmp/v15/loader.efi
python3 - <<'EOF'
import hashlib
h = hashlib.sha256(open('/tmp/v15/kernel','rb').read()).hexdigest()
assert not h.startswith('883e99e7'), 'kernel unchanged: the en0 driver did not get in'
k = open('/tmp/v15/kernel','rb').read()
for s in (b'en0_addr', b'10.0.0.2/30', b"the loader's channel", b'net ring'):
    assert s in k, 'kernel missing %s' % s
l = open('/tmp/v15/loader.efi','rb').read()
assert not hashlib.sha256(l).hexdigest().startswith('7ba818d2'), 'loader.efi unchanged'
for s in (b'oem netmode', b'oem netstat', b'the ring is on the page', b'D22AP'):
    assert s in l, 'loader missing %s' % s
print('kernel sha OK:', h[:16], '(carries loader_net/en0_addr strings)')
print('loader sha OK:', hashlib.sha256(l).hexdigest()[:16], '(net ring + netmode + D22AP identity)')
EOF
echo "-- v15 images (must equal the v14 payload's entries byte for byte):"
sha256sum $K/userland/flashboot.apfs $K/userland/root.apfs
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v15.bin" \
  --usb \
  loader.efi=/tmp/v15/loader.efi \
  kernel=/tmp/v15/kernel \
  resident=$K/userland/flashboot.apfs \
  ramdisk=$K/userland/root.apfs \
  cmdline=$R/device-layer/udon-hakios-cmdline-v15.bin \
  kernel.ver=/tmp/v15/kernel.ver \
  --no-version
python3 - "$R/device-layer/udon-hakios-payload-v15.bin" "$R/device-layer/udon-hakios-payload-v14.bin" <<'EOF'
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

v15 = entries(sys.argv[1])
v14 = entries(sys.argv[2])
names = sorted(v15)
assert names == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], names
assert v15['usb'] == b'1\x00', v15['usb']
assert v15['kernel.ver'] == v14['kernel.ver'], 'kernel.ver drifted'
assert v15['kernel'] != v14['kernel'], 'kernel is the v14 bytes'
assert v15['loader.efi'] != v14['loader.efi'], 'loader is the v14 bytes'
assert v15['resident'] == v14['resident'], 'resident drifted from the v14 entry'
assert v15['ramdisk'] == v14['ramdisk'], 'ramdisk drifted from the v14 entry'
print('entries:', sorted(v15))
print('resident/ramdisk == v14 entries byte-for-byte; kernel/loader/kernel.ver all as intended')
assert sum(len(v) for v in v15.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF
echo "-- payload v15:"
sha256sum "$R/device-layer/udon-hakios-payload-v15.bin"
ls -la "$R/device-layer/udon-hakios-payload-v15.bin"
