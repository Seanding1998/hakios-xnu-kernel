#!/bin/bash
# Wave 38 (wave38- prefix; the version number is confirmed with the main agent before any
# flash): the v27 payload with the self-heal loader and the v26 cmdline.
#
# Delta against v27's payload, entry by entry:
#   loader.efi -> the wave38 build (c82a35e4..., the USB pair self-heal: no-consumer-no-queue
#                 + stale-TRB drain + gated prints + the service window's whole-pair rebuild)
#   cmdline    -> the v26 characters (478 B, "... loader_return_after=600 ... gpu=1"). v27's
#                 " adreno_only=1" is wave37's step-1 probe diagnostic (forces newest_step=1);
#                 it is wave37's domain and is NOT carried into the USB self-heal image.
#   kernel / ramdisk / resident / kernel.ver / usb -> the v27 bytes (== v26 bytes, asserted)
set -e
R=/mnt/c/Users/<host>/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v38
rm -rf $TMP && mkdir -p $TMP

echo "-- extract the v27 payload's entries (loader.efi gets swapped, cmdline gets re-sourced from v26):"
python3 - "$R/device-layer/udon-hakios-payload-v27.bin" "$R/device-layer/udon-hakios-payload-v26.bin" <<'EOF'
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
    return out

v27 = entries(sys.argv[1])
v26 = entries(sys.argv[2])
assert sorted(v27) == sorted(v26) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v27[name] == v26[name], f'{name} drifted between v26 and v27'
    open('/tmp/v38/' + name, 'wb').write(v27[name])
    print('carried over:', name, len(v27[name]), 'bytes')
# the v26 cmdline: 477 chars + one trailing NUL, ending gpu=1, no adreno probe args
cmd = v26['cmdline']
assert len(cmd) == 478 and cmd.count(b'\0') == 1 and cmd.endswith(b'\0')
chars = cmd[:-1]
assert chars.endswith(b'gpu=1'), 'v26 cmdline tail anchor'
assert b'adreno_only' not in chars and b'adreno_fine' not in chars
assert b'loader_return_after=600' in chars and b'en0_addr=10.0.0.2' in chars
assert len(chars) + 110 <= 607, 'combined cmdline budget'
open('/tmp/v38/cmdline', 'wb').write(cmd)
print('cmdline re-sourced from v26:', len(cmd), 'B (478 = 477 chars + NUL), no adreno probe args')
EOF

echo "-- the wave38 loader.efi (built by build.sh with PAYLOAD_BASE=0xF4000000; sha pinned by verify):"
cp ~/hakios/kernel/xnuloader/loader.efi $TMP/loader.efi
sha256sum $TMP/loader.efi

echo "-- wave38 payload build:"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-wave38.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-wave38.bin" "$R/device-layer/udon-hakios-payload-v27.bin" <<'EOF'
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

w38 = entries(sys.argv[1])
v27 = entries(sys.argv[2])
assert sorted(w38) == sorted(v27) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb']
for name in ('kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert w38[name] == v27[name], f'{name} drifted from the v27 payload entry'
cmd = w38['cmdline']
assert cmd.count(b'\0') == 1 and cmd.endswith(b'\0'), 'cmdline must carry exactly one trailing NUL'
chars = cmd[:-1]
assert chars.endswith(b'gpu=1') and b'adreno_only' not in chars and b'adreno_fine' not in chars
assert b'loader_return_after=600' in chars and b'en0_addr=10.0.0.2' in chars
assert len(cmd) == 478
ldr = w38['loader.efi']
assert ldr != v27['loader.efi'], 'loader.efi must be the new build'
for s in (b'the IN gate is up', b'the bulk pair reads dead both ways', b'a reply came back unread'):
    assert s in ldr, f'wave38 self-heal string missing from the loader: {s}'
assert struct.unpack_from('<I', ldr, struct.unpack_from('<I', ldr, 0x3C)[0] + 40)[0] == 0x2140, 'entry RVA 0x2140'
assert hashlib.sha256(w38['kernel']).hexdigest().startswith('a39c931c')
assert hashlib.sha256(w38['ramdisk']).hexdigest().startswith('156b5be1')
assert sum(len(v) for v in w38.values()) < 0x4000000 - 0x1000
print(f"cmdline {len(cmd)} B (477 chars + NUL) == v26 bytes: gpu=1 carried, adreno probe args stay out")
print(f"loader.efi {len(ldr)} B sha {hashlib.sha256(ldr).hexdigest()[:16]} (the wave38 self-heal build)")
print(f"kernel {hashlib.sha256(w38['kernel']).hexdigest()[:16]} / ramdisk {hashlib.sha256(w38['ramdisk']).hexdigest()[:16]} == v27's byte for byte")
EOF

echo "-- payload wave38:"
sha256sum "$R/device-layer/udon-hakios-payload-wave38.bin"
