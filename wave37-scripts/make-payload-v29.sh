#!/bin/bash
# Wave 37 (v29): the v28 payload with the cape-gpucc kernel + the step-3 walk cmdline.
# v29 = v28 + kernel swap (e3852a0f -> the cape-gpucc build) + cmdline " adreno_only=1" -> " adreno=3":
# the machine walks steps 1,2,3 (1 proven by v28, 2 = plain fuse reads, 3 = the gpucc probe target with
# per-access prints on the newest step and 2200 ms pauses on its announcements; combined budget
# 110+486=596/607). ramdisk/loader/resident/kernel.ver/usb = v26..v28 bytes.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v29
mkdir -p $TMP

echo "-- extract the v28 payload's entries:"
python3 - "$R/device-layer/udon-hakios-payload-v28.bin" <<'EOF'
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
    open('/tmp/v29/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- swap in the fresh kernel + the walk cmdline:"
cp $K/hakios-kernel $TMP/kernel
python3 - <<'EOF'
import hashlib
k = open('/tmp/v29/kernel','rb').read()
assert not hashlib.sha256(k).hexdigest().startswith('e3852a0f'), 'kernel did not change'
data = open('/tmp/v29/cmdline', 'rb').read()
chars = data.split(b'\0', 1)[0]
assert chars.endswith(b'gpu=1 adreno_only=1'), 'v28 cmdline anchor missing'
new = chars[:-len(b' adreno_only=1')] + b' adreno=3\0'
assert len(new) == 487 and new.count(b'\0') == 1 and new.endswith(b'\0')
assert new.split(b'\0')[0].endswith(b'gpu=1 adreno=3')
assert len(new) - 1 + 110 <= 607
open('/tmp/v29/cmdline', 'wb').write(new)
open('/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave37-scripts/cmdline-v29.bin','wb').write(new)
print('kernel:', hashlib.sha256(k).hexdigest()[:16], '| cmdline 487 B (486 chars: gpu=1 adreno=3; budget 596/607)')
EOF

echo "-- v29 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v29.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v29.bin" "$R/device-layer/udon-hakios-payload-v28.bin" <<'EOF'
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

v29 = entries(sys.argv[1])
v28 = entries(sys.argv[2])
assert sorted(v29) == sorted(v28) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v29[name] == v28[name], f'{name} drifted from the v28 payload entry'
assert v29['kernel'] != v28['kernel'], 'kernel entry must differ'
assert v29['cmdline'] != v28['cmdline'], 'cmdline entry must differ (adreno=3)'
assert hashlib.sha256(v29['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v29.values()) < 0x4000000 - 0x1000
print(f"kernel {hashlib.sha256(v29['kernel']).hexdigest()[:16]} (was e3852a0f...); all else byte-equal v28")
EOF

echo "-- payload v29:"
sha256sum "$R/device-layer/udon-hakios-payload-v29.bin"
