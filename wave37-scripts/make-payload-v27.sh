#!/bin/bash
# Wave 37 (v27): the v26 payload with the step-1 probe cmdline.
#
# v27 cmdline = the v26 characters (477, loader_return_after=600 + gpu=1 inside the string)
# + " adreno_only=1" + one NUL = 491 chars + NUL = 492 B; combined echo budget 110+491=601/607
# (the loader's 110-char header + payload cmdline, truncated past 607 -- loader.c:3617-3625;
# wave23 ground truth). adreno_only=1 forces newest_step=1: get()/get8() print "about to read"
# before every step-1 access, so the logdump names the exact register the machine hangs on.
# adreno_fine=1 was deliberately LEFT OUT: it is inert under gpu=1 (pause_ms=0 -> hold() no-ops)
# and its 14 chars would push the payload cmdline to 505 > 497 -> truncated tail.
# Everything else = the v26 bytes (kernel a39c931c, ramdisk 156b5be1, loader 0ade78b5, etc.).
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v27
mkdir -p $TMP

echo "-- extract the v26 payload's entries (v26 already carries the right kernel/ramdisk/loader):"
python3 - "$R/device-layer/udon-hakios-payload-v26.bin" <<'EOF'
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
    open('/tmp/v27/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- the v27 cmdline (v26 characters + the step-1 probe arg, before the NUL):"
python3 - <<'EOF'
data = open('/tmp/v27/cmdline', 'rb').read()
# v26's cmdline: 477 characters + one trailing NUL, ending "... en0_addr=10.0.0.2 gpu=1".
chars = data.split(b'\0', 1)[0]
assert len(data) == 478 and data.count(b'\0') == 1 and data.endswith(b'\0'), 'v26 cmdline not as expected'
assert chars.endswith(b'gpu=1') and chars.count(b'gpu=1') == 1, 'gpu=1 anchor missing'
assert b'adreno_only' not in chars, 'probe arg already present'
new = chars + b' adreno_only=1\0'
assert len(new) == 492, len(new)                       # 477 chars + 14 (" adreno_only=1") + 1 NUL
assert new.count(b'\0') == 1 and new.endswith(b'\0')
assert new.split(b'\0')[0].endswith(b'adreno_only=1')
# combined-line budget: 110 (loader header) + 491 = 601 of 607 -- fits, no truncation
assert len(new) - 1 + 110 <= 607
open('/tmp/v27/cmdline.new', 'wb').write(new)
open('/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110/wave37-scripts/cmdline-v27.bin', 'wb').write(new)
print('cmdline.new: %d bytes (%d chars + NUL); tail: %r' % (len(new), len(new) - 1, new[-40:]))
EOF

echo "-- v27 payload build (cmdline swapped, all else = v26 bytes):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v27.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline.new \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v27.bin" "$R/device-layer/udon-hakios-payload-v26.bin" <<'EOF'
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

v27 = entries(sys.argv[1])
v26 = entries(sys.argv[2])
assert sorted(v27) == sorted(v26) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v27[name] == v26[name], f'{name} drifted from the v26 payload entry'
cmd = v27['cmdline']
assert cmd.count(b'\0') == 1 and cmd.endswith(b'\0'), 'cmdline must carry exactly one trailing NUL'
chars = cmd[:-1]
assert chars.count(b'adreno_only=1') == 1 and chars.endswith(b'gpu=1 adreno_only=1')
assert b'adreno_fine' not in chars, 'adreno_fine must stay out (budget 497)'
assert b'loader_return_after=600' in chars and b'gpu=1' in chars and b'en0_addr=10.0.0.2' in chars
assert len(cmd) == 492
assert hashlib.sha256(v27['kernel']).hexdigest().startswith('a39c931c')
assert hashlib.sha256(v27['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v27.values()) < 0x4000000 - 0x1000
print(f"cmdline {len(cmd)} B (491 chars + NUL): adreno_only=1 BEFORE the NUL (combined budget 601/607)")
print(f"kernel {hashlib.sha256(v27['kernel']).hexdigest()[:16]} / ramdisk {hashlib.sha256(v27['ramdisk']).hexdigest()[:16]} == v26's byte for byte")
EOF

echo "-- payload v27:"
sha256sum "$R/device-layer/udon-hakios-payload-v27.bin"
