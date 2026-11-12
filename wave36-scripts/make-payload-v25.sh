#!/bin/bash
# Wave 36 (v25) payload: the GPU first-light build.
#   kernel  = the gen7 parameter-layer build (a39c931c..., the wave36 apply-adreno patch,
#             CONFIG_HAKIOS_ADRENO=y; the v24 kernel abecd557 is replaced for the first time
#             since wave 26)
#   ramdisk = root.apfs rebuilt by the v13 recipe (FLASHBOOT=1 CRYPTEXES=flash RC_JOBS=rc.jobs.ssh)
#             with the pulled a730 firmware trio (+ zap segments) stored plain under fw/
#             [156b5be1...]; the init re-entry guard of wave 34 rides in it unchanged.
#   cmdline = the v24 bytes + " gpu=1" (the boot-arg that makes the driver start by itself and
#             keep the GPU on; 473 -> 479 bytes, budget 581/607)
#   loader.efi, resident, kernel.ver, usb = the v24 entries byte for byte (the resident is the
#             v23-era flashboot.apfs carried through v24; the fresh build.sh output is NOT used
#             for it, same policy as waves 23/24).
# Firmware channel decision (task asked for one): the tree's own convention is root.apfs /fw/
# (hakios.image.c reads "fw/NAME" from the image that travels with the kernel; userland/build.sh
# copies ../fw-gpu into it, "--plain fw"). No new payload entry, so PAYLOAD_BASE layout and the
# loader stay untouched.
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
K=/home/cyrux/hakios/kernel
TMP=/tmp/v25
mkdir -p $TMP

echo "-- extract the v24 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v24.bin" <<'EOF'
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
    open('/tmp/v25/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- the v25 kernel (must be a39c931c, NOT the v24 abecd557):"
sha256sum $K/hakios-kernel
cp $K/hakios-kernel /tmp/v25/kernel

echo "-- the v25 ramdisk (root.apfs with fw/, must be 156b5be1):"
sha256sum $K/userland/root.apfs
cp $K/userland/root.apfs /tmp/v25/ramdisk

echo "-- the v25 cmdline (v24 bytes + gpu=1):"
python3 - <<'EOF'
data = open('/tmp/v25/cmdline', 'rb').read()
assert b'gpu=1' not in data, 'cmdline already carries gpu=1'
assert b'en0_addr=10.0.0.2' in data and b'loader_return_after=1800' in data
new = data + b' gpu=1'
assert len(new) == len(data) + 6, len(new)
open('/tmp/v25/cmdline.new', 'wb').write(new)
print('cmdline.new: %d bytes: %s' % (len(new), new.decode()))
EOF

echo "-- v25 payload build (kernel+ramdisk+cmdline swapped, all else pinned to v24):"
cd $K/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v25.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline.new \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v25.bin" "$R/device-layer/udon-hakios-payload-v24.bin" <<'EOF'
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

v25 = entries(sys.argv[1])
v24 = entries(sys.argv[2])
assert sorted(v25) == sorted(v24) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v25)
for name in ('loader.efi', 'kernel.ver', 'resident', 'usb'):
    assert v25[name] == v24[name], f'{name} drifted from the v24 payload entry'
assert v25['kernel'] != v24['kernel'] and hashlib.sha256(v25['kernel']).hexdigest().startswith('a39c931c')
assert v25['ramdisk'] != v24['ramdisk'] and hashlib.sha256(v25['ramdisk']).hexdigest().startswith('156b5be1')
cmd = v25['cmdline']
assert cmd == v24['cmdline'] + b' gpu=1'
assert b'loader_return_after=1800' in cmd and b'en0_addr=10.0.0.2' in cmd
fw_markers = [b'gmu_gen70000.bin', b'a730_sqe.fw', b'a730_zap.mdt']
assert all(m in v25['ramdisk'] for m in fw_markers), 'firmware names missing from the ramdisk entry'
assert len(cmd) == 479 and len(cmd) <= 607 - 110
print(f"cmdline {len(cmd)} B: +gpu=1 (budget 581/607)")
print(f"kernel {hashlib.sha256(v25['kernel']).hexdigest()[:16]} (was abecd557), ramdisk {hashlib.sha256(v25['ramdisk']).hexdigest()[:16]} (was 61323255)")
print("carry byte-for-byte:", ', '.join(n for n in ('loader.efi', 'kernel.ver', 'resident', 'usb')))
assert sum(len(v) for v in v25.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v25:"
sha256sum "$R/device-layer/udon-hakios-payload-v25.bin"
ls -la "$R/device-layer/udon-hakios-payload-v25.bin"
