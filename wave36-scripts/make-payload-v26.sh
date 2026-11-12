#!/bin/bash
# Wave 36 (v26): the v25 content with the FIXED cmdline.
#
# The v25 bug (gen-2 console forensic): the payload cmdline is a NUL-terminated string;
# the v24 entry is 473 B = 472 characters + the trailing NUL. make-payload-v25.sh built
# v25's cmdline as v24bytes + " gpu=1", which put " gpu=1" AFTER that NUL. The loader
# reads pi.cmdline as a C string and stops at the first NUL, so the kernel received the
# v24 arguments and nothing else (console echo measured 582/607 -- the budget was never
# the problem; the adreno driver never ran, zero "adreno:" lines in the gen-2 console).
#
# v26 cmdline = (v24 characters with loader_return_after 1800->600, per the user's
# speed order) + " gpu=1" + one NUL. 477 characters + NUL = 478 B; budget 581/607.
# Everything else = the v25 bytes (kernel a39c931c, ramdisk 156b5be1, loader/resident/
# kernel.ver/usb the v24 carries).
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v26
mkdir -p $TMP

echo "-- extract the v25 payload's entries (v25 already carries the right kernel/ramdisk):"
python3 - "$R/device-layer/udon-hakios-payload-v25.bin" <<'EOF'
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
    open('/tmp/v26/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- the v26 cmdline (NUL-placement fixed + loader_return_after 600):"
python3 - <<'EOF'
data = open('/tmp/v26/cmdline', 'rb').read()
# v25's cmdline: 472 characters, NUL, " gpu=1" (the bug). Take the characters BEFORE
# the first NUL, swap the return timer, append gpu=1, terminate with exactly one NUL.
chars = data.split(b'\0', 1)[0]
old = b'loader_return_after=1800'
assert chars.count(old) == 1 and b'gpu=1' not in chars, 'cmdline anchor not as expected'
chars = chars.replace(old, b'loader_return_after=600')
new = chars + b' gpu=1\0'
assert len(new) == 478, len(new)   # 472 chars - 1 (1800->600) + 6 (" gpu=1") + 1 NUL
assert new.count(b'\0') == 1 and new.endswith(b'\0')
assert new.split(b'\0')[0].endswith(b'gpu=1')
open('/tmp/v26/cmdline.new', 'wb').write(new)
print('cmdline.new: %d bytes; tail: %r' % (len(new), new[-40:]))
EOF

echo "-- v26 payload build (cmdline swapped, all else = v25 bytes):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v26.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline.new \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v26.bin" "$R/device-layer/udon-hakios-payload-v25.bin" <<'EOF'
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

v26 = entries(sys.argv[1])
v25 = entries(sys.argv[2])
assert sorted(v26) == sorted(v25) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('loader.efi', 'kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v26[name] == v25[name], f'{name} drifted from the v25 payload entry'
cmd = v26['cmdline']
assert cmd.count(b'\0') == 1 and cmd.endswith(b'\0'), 'cmdline must carry exactly one trailing NUL'
chars = cmd[:-1]
assert chars.count(b'gpu=1') == 1 and chars.endswith(b'en0_addr=10.0.0.2 gpu=1')
assert b'loader_return_after=600' in chars and b'loader_return_after=1800' not in chars
assert b'en0_addr=10.0.0.2' in chars and len(cmd) == 478
assert hashlib.sha256(v26['kernel']).hexdigest().startswith('a39c931c')
assert hashlib.sha256(v26['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in v26.values()) < 0x4000000 - 0x1000
print(f"cmdline {len(cmd)} B (476 chars + NUL): loader_return_after=600, gpu=1 BEFORE the NUL (budget 581/607)")
print(f"kernel {hashlib.sha256(v26['kernel']).hexdigest()[:16]} / ramdisk {hashlib.sha256(v26['ramdisk']).hexdigest()[:16]} == v25's byte for byte")
EOF

echo "-- payload v26:"
sha256sum "$R/device-layer/udon-hakios-payload-v26.bin"
