#!/bin/bash
# Wave 26 Round 3 (v23) payload: the v22 payload with only the cmdline swapped --
# loader_return_after 180 -> 1800 (the 180 s hard session cap is what killed every
# SSH attempt: sshd listens at ~165 s and the return began at 180 s). The cmdline
# grows by one character (472 -> 473 bytes with the NUL; budget 471+110=581/607).
# Every other entry stays byte-for-byte the v22 payload's.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v23
mkdir -p $TMP

echo "-- extract the v22 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v22.bin" <<'EOF'
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
    open('/tmp/v23/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- the v23 cmdline (one byte-range moved):"
python3 - <<'EOF'
data = open('/tmp/v23/cmdline', 'rb').read()
old = b'loader_return_after=180'
assert data.count(old) == 1 and b'loader_return_after=1800' not in data, 'cmdline anchor not as expected'
new = data.replace(old, b'loader_return_after=1800')
assert len(new) == len(data) + 1, len(new)
open('/tmp/v23/cmdline.new', 'wb').write(new)
print('cmdline.new: %d bytes; %s' % (len(new), new.decode().replace('loader_return_after=1800', '[loader_return_after=1800]')[:120]))
EOF

echo "-- v23 payload build (cmdline swapped, all else pinned to v22):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v23.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline.new \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v23.bin" "$R/device-layer/udon-hakios-payload-v22.bin" <<'EOF'
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

v23 = entries(sys.argv[1])
v22 = entries(sys.argv[2])
assert sorted(v23) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v23)
for name in ('loader.efi', 'kernel', 'kernel.ver', 'resident', 'ramdisk', 'usb'):
    assert v23[name] == v22[name], f'{name} drifted from the v22 payload entry'
cmd = v23['cmdline']
assert cmd.count(b'loader_return_after=1800') == 1 and b'loader_return_after=180\x00' not in cmd
assert b'en0_addr=10.0.0.2' in cmd and b'rec_secs' not in cmd
assert len(cmd) <= 607 - 110, f'cmdline over budget: {len(cmd)}'
assert len(cmd) == 473, f'cmdline length: {len(cmd)}'
print(f"cmdline {len(cmd)} B: loader_return_after=1800 (the session cap lifted; budget 581/607)")
print(f"loader {hashlib.sha256(v23['loader.efi']).hexdigest()[:16]} / kernel {hashlib.sha256(v23['kernel']).hexdigest()[:16]} == v22's byte for byte")
assert sum(len(v) for v in v23.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v23:"
sha256sum "$R/device-layer/udon-hakios-payload-v23.bin"
