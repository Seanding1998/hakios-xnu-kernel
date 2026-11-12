#!/bin/bash
# Wave 38 (v34; the version number assigned by the main agent, v27-v33 are wave37's):
# the re-baselined merge = v33's payload entries (kernel 55a8d40f, the GPU-first-light
# build; cmdline = the v26/v33 bytes gpu=1) + the wave38 self-heal loader.efi (3f595c52).
# Delta against v33's payload, entry by entry:
#   loader.efi -> the wave38 USB pair self-heal build (3f595c52...)
#   kernel / cmdline / ramdisk / resident / kernel.ver / usb -> the v33 bytes (asserted)
# NOTE: loader builds are NOT reproducible (PE timestamp) -- the loader.efi consumed here
# is the pinned tree artifact ~/hakios/kernel/xnuloader/loader.efi (3f595c52); build.sh
# must NOT be re-run after verify-green.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v34
rm -rf $TMP && mkdir -p $TMP

echo "-- extract the v33 payload's entries (kernel/cmdline are the base, loader gets swapped):"
python3 - "$R/device-layer/udon-hakios-payload-v33.bin" <<'EOF'
import struct, hashlib, sys
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
    assert off == 8 + size
    return out

v33 = entries(sys.argv[1])
assert sorted(v33) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
assert hashlib.sha256(v33['kernel']).hexdigest().startswith('55a8d40f'), 'v33 kernel anchor'
cmd = v33['cmdline']
assert len(cmd) == 478 and cmd.count(b'\0') == 1 and cmd.endswith(b'\0')
assert cmd[:-1].endswith(b'gpu=1'), 'cmdline tail anchor'
assert b'adreno_only' not in cmd and b'adreno_fine' not in cmd
for name in v33:
    open('/tmp/v34/' + name, 'wb').write(v33[name])
    print('carried over:', name, len(v33[name]), 'bytes, sha', hashlib.sha256(v33[name]).hexdigest()[:16])
EOF

echo "-- swap in the wave38 self-heal loader (the pinned tree artifact, NOT a rebuild):"
cp ~/hakios/kernel/xnuloader/loader.efi $TMP/loader.efi
sha256sum $TMP/loader.efi

echo "-- swap the ramdisk to the wave39 GL=test carrier (main-agent addendum; sole delta vs the run above):"
GL_RD=/home/cyrux/hakios/kernel/userland/root.apfs
python3 - "$GL_RD" <<'EOF'
import hashlib, sys
d = open(sys.argv[1], 'rb').read()
assert hashlib.sha256(d).hexdigest().startswith('c2780842'), 'GL=test carrier anchor (c2780842)'
assert len(d) == 8089600, len(d)
assert d[32:36] == b'NXSB', 'APFS container'
for s in (b'gl_test', b'u2f_test', b'libOSMesa'):
    assert s in d, f'GL carrier content missing: {s}'
open('/tmp/v34/ramdisk', 'wb').write(d)
print('ramdisk = the GL=test carrier:', len(d), 'bytes, sha', hashlib.sha256(d).hexdigest()[:16])
EOF
sha256sum $TMP/ramdisk

echo "-- v34 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v34.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v34.bin" "$R/device-layer/udon-hakios-payload-v33.bin" <<'EOF'
import hashlib, struct, sys

def entries(path):
    data = open(path, 'rb').read()
    magic, size = struct.unpack_from('<II', data, 0)
    assert magic == 0x50554E58
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
    return out

v34 = entries(sys.argv[1])
v33 = entries(sys.argv[2])
assert sorted(v34) == sorted(v33) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('kernel', 'cmdline', 'resident', 'kernel.ver', 'usb'):
    assert v34[name] == v33[name], f'{name} drifted from the v33 payload entry'
ldr = v34['loader.efi']
assert ldr != v33['loader.efi'], 'loader.efi must be the new build'
assert hashlib.sha256(ldr).hexdigest().startswith('3f595c52'), 'wave38 loader anchor'
for s in (b'the IN gate is up', b'the bulk pair reads dead both ways', b'a reply came back unread'):
    assert s in ldr, f'wave38 self-heal string missing: {s}'
assert struct.unpack_from('<I', ldr, struct.unpack_from('<I', ldr, 0x3C)[0] + 40)[0] == 0x2140, 'entry RVA 0x2140'
assert hashlib.sha256(v34['kernel']).hexdigest().startswith('55a8d40f')
assert hashlib.sha256(v34['ramdisk']).hexdigest().startswith('c2780842'), 'ramdisk must be the GL=test carrier'
assert len(v34['ramdisk']) == 8089600
assert b'gl_test' in v34['ramdisk'] and b'libOSMesa' in v34['ramdisk']
assert sum(len(v) for v in v34.values()) < 0x4000000 - 0x1000
print(f"loader.efi {len(ldr)} B sha {hashlib.sha256(ldr).hexdigest()[:16]} (the wave38 self-heal build)")
print(f"kernel {hashlib.sha256(v34['kernel']).hexdigest()[:16]} / cmdline {len(v34['cmdline'])} B / ramdisk {hashlib.sha256(v34['ramdisk']).hexdigest()[:16]} == v33's byte for byte")
EOF

echo "-- payload v34:"
sha256sum "$R/device-layer/udon-hakios-payload-v34.bin"
