#!/bin/bash
# Wave 42 (v35; v27-v33 are wave37's, v34 was the reviewed-loader re-baseline):
# the v35 merge = v33's payload entries (kernel 55a8d40f the GPU-first-light build,
# cmdline = the v26/v33 bytes gpu=1) + the wave39 GL=test ramdisk (c2780842) +
# the v35 loader.efi (5de055ea = the GEN-1..4 fix chain built on the v42 root fix:
# the LLVM 22.1.8 -O1 elimination was root-fixed by making the GEN-4 stamp globals
# volatile; three-level obj/reloc/efi assertions green; suites 49/0 + 22/22).
# Delta against v33's payload, entry by entry:
#   loader.efi -> the v35 build (5de055ea, as-built sha pin; NOT reproducible -- PE
#                 timestamp; build.sh must NOT be re-run after verify-green)
#   ramdisk    -> the wave39 GL=test carrier c2780842
#   kernel / cmdline / resident / kernel.ver / usb -> the v33 bytes (asserted)
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/w35
rm -rf $TMP && mkdir -p $TMP

echo "-- extract the v33 payload's entries (kernel/cmdline are the base, loader+ramdisk get swapped):"
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
    open('/tmp/w35/' + name, 'wb').write(v33[name])
    print('carried over:', name, len(v33[name]), 'bytes, sha', hashlib.sha256(v33[name]).hexdigest()[:16])
EOF

echo "-- swap in the v35 loader (the pinned tree artifact loader.efi = 5de055ea, NOT a rebuild):"
cp ~/hakios/kernel/xnuloader/loader.efi $TMP/loader.efi
sha256sum $TMP/loader.efi

echo "-- swap the ramdisk to the wave39 GL=test carrier (c2780842): pinned extract from the"
echo "   v34-GL payload (udon-hakios-payload-v34.bin) -- the WSL tree's root.apfs was"
echo "   rebuilt by wave41 to the NEW carrier 51a030c3 (reserved for v36; the coordinator's"
echo "   variable-isolation order keeps v35 on the old carrier), so the c2780842 bytes are"
echo "   pinned once into device-layer/root-apfs-c2780842.bin:"
GL_RD=$R/device-layer/root-apfs-c2780842.bin
if [ ! -f "$GL_RD" ]; then
  python3 - "$R/device-layer/udon-hakios-payload-v34.bin" "$GL_RD" <<'EOF'
import hashlib, struct, sys
data = open(sys.argv[1], 'rb').read()
magic, size = struct.unpack_from('<II', data, 0)
assert magic == 0x50554E58
off = 8
while off < 8 + size:
    name, esize, _ = struct.unpack_from('<16sII', data, off)
    name = name.rstrip(b'\0').decode()
    off += 24
    if name == '':
        break
    if name == 'ramdisk':
        d = data[off:off + esize]
        break
    off += esize + (-esize % 16)
assert hashlib.sha256(d).hexdigest().startswith('c2780842'), 'GL=test carrier anchor (c2780842)'
assert len(d) == 8089600, len(d)
assert d[32:36] == b'NXSB', 'APFS container'
for s in (b'gl_test', b'u2f_test', b'libOSMesa'):
    assert s in d, f'GL carrier content missing: {s}'
open(sys.argv[2], 'wb').write(d)
print('pinned:', sys.argv[2], len(d), 'bytes, sha', hashlib.sha256(d).hexdigest()[:16])
EOF
fi
cp "$GL_RD" $TMP/ramdisk
python3 - "$GL_RD" <<'EOF'
import hashlib, sys
d = open(sys.argv[1], 'rb').read()
assert hashlib.sha256(d).hexdigest().startswith('c2780842'), 'GL carrier anchor'
assert len(d) == 8089600 and d[32:36] == b'NXSB'
print('ramdisk = the GL=test carrier:', len(d), 'bytes, sha', hashlib.sha256(d).hexdigest()[:16])
EOF
sha256sum $TMP/ramdisk

echo "-- v35 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v35.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v35.bin" "$R/device-layer/udon-hakios-payload-v33.bin" <<'EOF'
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

v35 = entries(sys.argv[1])
v33 = entries(sys.argv[2])
assert sorted(v35) == sorted(v33) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('kernel', 'cmdline', 'resident', 'kernel.ver', 'usb'):
    assert v35[name] == v33[name], f'{name} drifted from the v33 payload entry'
ldr = v35['loader.efi']
assert ldr != v33['loader.efi'], 'loader.efi must be the new build'
assert hashlib.sha256(ldr).hexdigest().startswith('5de055ea'), 'v35 loader anchor (5de055ea)'
for s in (b'the IN gate is up', b'the pair reads dead in this generation',
          b'bounded recovery %d of 2', b"the recovery's bring-up is back",
          b'a reply came back unread'):
    assert s in ldr, f'v35 loader string missing: {s}'
assert struct.unpack_from('<I', ldr, struct.unpack_from('<I', ldr, 0x3C)[0] + 40)[0] == 0x2140, 'entry RVA 0x2140'
assert hashlib.sha256(v35['kernel']).hexdigest().startswith('55a8d40f')
assert hashlib.sha256(v35['ramdisk']).hexdigest().startswith('c2780842'), 'ramdisk must be the GL=test carrier'
assert len(v35['ramdisk']) == 8089600
assert b'gl_test' in v35['ramdisk'] and b'libOSMesa' in v35['ramdisk']
assert sum(len(v) for v in v35.values()) < 0x4000000 - 0x1000
print(f"loader.efi {len(ldr)} B sha {hashlib.sha256(ldr).hexdigest()[:16]} (the v35 build)")
print(f"kernel {hashlib.sha256(v35['kernel']).hexdigest()[:16]} / cmdline {len(v35['cmdline'])} B == v33's byte for byte; ramdisk {hashlib.sha256(v35['ramdisk']).hexdigest()[:16]}")
EOF

echo "-- payload v35:"
sha256sum "$R/device-layer/udon-hakios-payload-v35.bin"
