#!/bin/bash
# Wave 45 (v36; v35 is wave42's shipped generation): the v36 merge =
#   loader.efi -> the v35 build 5de055ea (FROZEN: the tree file as-is, no rebuild),
#   kernel     -> 5b77b418 (wave43's build = wave41 GPU fixes + the fuelgauge driver, same tree),
#   ramdisk    -> 51a030c3 (the wave41 GL=test carrier: gl_test with the real judge inside),
#   cmdline    -> the v35 bytes with " fuelgauge=2" appended (split(NUL)[0] + new + NUL),
#   resident / kernel.ver / usb -> the v35 bytes, asserted byte for byte.
# The swap is expressed against the SHIPPED v35 payload (device-layer/udon-hakios-payload-v35.bin),
# never against the tree, and every carried entry is asserted.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/w45
rm -rf $TMP && mkdir -p $TMP

echo "-- extract the v35 payload's entries (everything except kernel/ramdisk/cmdline is carried):"
python3 - "$R/device-layer/udon-hakios-payload-v35.bin" <<'EOF'
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

v35 = entries(sys.argv[1])
assert sorted(v35) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
assert hashlib.sha256(v35['kernel']).hexdigest().startswith('55a8d40f'), 'v35 kernel anchor'
assert hashlib.sha256(v35['loader.efi']).hexdigest().startswith('5de055ea'), 'v35 loader anchor'
assert hashlib.sha256(v35['ramdisk']).hexdigest().startswith('c2780842'), 'v35 ramdisk anchor'
cmd = v35['cmdline']
assert len(cmd) == 478 and cmd.count(b'\0') == 1 and cmd.endswith(b'\0')
assert cmd[:-1].endswith(b'gpu=1'), 'cmdline tail anchor'
assert b'fuelgauge' not in cmd, 'v35 cmdline must not already carry fuelgauge'
for name in v35:
    open('/tmp/w45/' + name, 'wb').write(v35[name])
    print('carried over:', name, len(v35[name]), 'bytes, sha', hashlib.sha256(v35[name]).hexdigest()[:16])
EOF

echo "-- kernel: the frozen wave43 build (5b77b418) straight from the tree, NOT a rebuild:"
cp /home/cyrux/hakios/kernel/hakios-kernel $TMP/kernel
sha256sum $TMP/kernel

echo "-- ramdisk: the frozen wave41 GL=test carrier (51a030c3) straight from the tree:"
cp /home/cyrux/hakios/kernel/userland/root.apfs $TMP/ramdisk
sha256sum $TMP/ramdisk

echo "-- cmdline: the v35 text + ' fuelgauge=2' + NUL (the wave43 s8 append rule):"
python3 - <<'EOF'
cmd = open('/tmp/w45/cmdline', 'rb').read()
assert cmd.endswith(b'\0') and cmd.count(b'\0') == 1
new = cmd[:-1] + b' fuelgauge=2\0'
open('/tmp/w45/cmdline', 'wb').write(new)
print('cmdline: %d -> %d bytes; text tail: %r' % (len(cmd), len(new), new[:-1][-40:]))
EOF

echo "-- loader: the v35 build from the tree (byte-equality against the v35 payload's entry is asserted after the pack):"
cp /home/cyrux/hakios/kernel/xnuloader/loader.efi $TMP/loader.efi
python3 - <<'EOF'
import hashlib
a = open('/tmp/w45/loader.efi', 'rb').read()
print('loader.efi', len(a), 'B sha', hashlib.sha256(a).hexdigest()[:16])
EOF

echo "-- v36 payload build:"
cd /home/cyrux/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v36.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v36.bin" "$R/device-layer/udon-hakios-payload-v35.bin" <<'EOF'
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

v36 = entries(sys.argv[1])
v35 = entries(sys.argv[2])
assert sorted(v36) == sorted(v35) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'resident', 'kernel.ver', 'usb'):
    assert v36[name] == v35[name], f'{name} drifted from the v35 payload entry'
ldr = v36['loader.efi']
assert hashlib.sha256(ldr).hexdigest().startswith('5de055ea'), 'loader anchor (5de055ea, frozen)'
assert len(ldr) == 90112
for s in (b'the IN gate is up', b'the pair reads dead in this generation',
          b'bounded recovery %d of 2', b"the recovery's bring-up is back",
          b'a reply came back unread'):
    assert s in ldr, f'loader string missing: {s}'
k = v36['kernel']
assert hashlib.sha256(k).hexdigest().startswith('5b77b418'), 'kernel anchor (5b77b418)'
assert k != v35['kernel'], 'kernel must be the new build'
assert len(k) == 15121752
for s in (b'gmu_gen70000.bin', b'a730_sqe.fw', b'a730_zap.mdt', b'a730_zap.b01',
          b'an Adreno 730v3 (chip id 0x7030002)', b'tcm_ret_cntl', b'general_10',
          b'the feeder is in: the ring', b'the stage has no room',
          b'MiniIOMobileFramebuffer', b'MiniIOSurface', b'IOCoreSurfaceRoot',
          b'created surface %u: %ux%u'):
    assert s in k, f'kernel heritage string missing: {s}'
for s in (b'fuelgauge', b'the gauge answers', b'the PMIC arbiter is version',
          b'adreno_ddr_type', b'gras_nc_mode_cntl', b'fuelgauge_poll_us'):
    assert s in k, f'kernel wave41/43 string missing: {s}'
rd = v36['ramdisk']
assert hashlib.sha256(rd).hexdigest().startswith('51a030c3'), 'ramdisk anchor (51a030c3)'
assert len(rd) == 8089600 and rd[32:36] == b'NXSB'
assert b'gl_test' in rd and b'libOSMesa' in rd and b'u2f_test' in rd
cmd = v36['cmdline']
assert cmd.count(b'\0') == 1 and cmd.endswith(b'\0')
assert cmd[:-1].endswith(b'gpu=1 fuelgauge=2'), 'cmdline tail anchor'
assert cmd[:477] == v35['cmdline'][:477], 'cmdline prefix must be the v35 text byte for byte'
assert len(cmd) == 490, len(cmd)
assert sum(len(v) for v in v36.values()) < 0x4000000 - 0x1000
print(f"loader.efi {len(ldr)} B sha 5de055ea (frozen v35 build)")
print(f"kernel {hashlib.sha256(k).hexdigest()[:16]} ({len(k)} B) = wave41 GPU fixes + wave43 fuelgauge")
print(f"ramdisk {hashlib.sha256(rd).hexdigest()[:16]} (the wave41 GL=test carrier)")
print(f"cmdline {len(cmd) - 1} chars == v35 text + ' fuelgauge=2'")
EOF

echo "-- payload v36:"
sha256sum "$R/device-layer/udon-hakios-payload-v36.bin"
