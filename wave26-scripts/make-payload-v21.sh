#!/bin/bash
# Wave 26 (K1 fix) payload: the v20 payload with only the kernel swapped for the Wave 26 build
# (hakios.loader_net.c: the poll never touches the stack any more -- stage + feeder thread + the
# "seen" heartbeat). loader.efi/resident/ramdisk/cmdline/kernel.ver/usb are the v20 payload's
# entries byte for byte; the cmdline is the v17/v18 file bytes (loader_return_after=180,
# en0_addr=10.0.0.2, no rec_*).
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v21
mkdir -p $TMP

echo "-- extract the v20 payload's entries (the pin sources):"
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
    open('/tmp/v21/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- the new kernel (the only entry that moves):"
cp -p $HOME/hakios/kernel/hakios-kernel /tmp/v21/kernel.new
sha256sum /tmp/v21/kernel.new
grep -c "the feeder is in" /tmp/v21/kernel.new >/dev/null || { echo "new kernel lacks the Wave 26 feeder marker"; exit 1; }

echo "-- v21 payload build (kernel swapped, all else pinned to the v20 payload):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v21.bin" \
  --usb \
  loader.efi=$TMP/loader.efi \
  kernel=$TMP/kernel.new \
  resident=$TMP/resident \
  ramdisk=$TMP/ramdisk \
  cmdline=$TMP/cmdline \
  kernel.ver=$TMP/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v21.bin" "$R/device-layer/udon-hakios-payload-v24.bin" "$R/device-layer/udon-hakios-cmdline-v17.bin" <<'EOF'
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

v21 = entries(sys.argv[1])
v20 = entries(sys.argv[2])
cmdfile = open(sys.argv[3], 'rb').read()
assert sorted(v21) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v21)
for name in ('loader.efi', 'kernel.ver', 'cmdline', 'resident', 'ramdisk', 'usb'):
    assert v21[name] == v20[name], f'{name} drifted from the v20 payload entry'
assert v21['cmdline'] == cmdfile, 'cmdline is not the v17/v18 file bytes'
assert b'loader_return_after=180' in v21['cmdline'] and b'en0_addr=10.0.0.2' in v21['cmdline']
assert b'rec_secs' not in v21['cmdline'], 'the recording boot-args must stay out'
k = v21['kernel']
assert k != v20['kernel'], 'kernel is not the Wave 26 build'
assert hashlib.sha256(v20['kernel']).hexdigest().startswith('17c905ec'), 'the v20 kernel pin moved'
for s in (b'the feeder is in: the ring', b'the stage has no room'):
    assert s in k, f'new kernel missing {s}'
l = v21['loader.efi']
lh = hashlib.sha256(l).hexdigest()
assert lh.startswith('b8a2150b'), f'loader.efi is not the Wave 24 build: {lh[:16]}'
for s in (b'checkpoint-1: the standing receive is in',
          b'checkpoint-3: the standing receive finished',
          b'the console mirror: vendor door',
          b'the bring-up begins (the Wave 24 timeline runs from here)'):
    assert s in l, f'v24 loader missing {s}'
import struct as st
found = None
for m in range(0, len(l) - 40, 4):
    if st.unpack_from('<I', l, m)[0] == 0x52BE8008:      # movz w?, #0xF400, lsl #16
        for kk in (1, 2, 3, 4, 5, 6):
            if st.unpack_from('<I', l, m + 4 * kk)[0] == 0x72AA0AB3:   # movk w?, #0x5055, lsl #16
                found = (m, kk)
                break
        if found:
            break
assert found, 'PAYLOAD_BASE pin: no movz #0xF400 near the XNUP magic movk'
print(f"loader.efi {lh[:16]} (the Wave 24 build, byte-for-byte the v20 payload's)")
print(f"kernel {hashlib.sha256(k).hexdigest()[:16]} (Wave 26: the K1 feeder build; v20 was 17c905ec)")
print(f"PAYLOAD_BASE pin: movz #0xF400 at {hex(found[0])}, the XNUP movk {found[1] * 4} bytes later")
print('loader/cmdline/resident/ramdisk/kernel.ver/usb == v20 payload entries byte-for-byte')
assert sum(len(v) for v in v21.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v21:"
sha256sum "$R/device-layer/udon-hakios-payload-v21.bin"
cp -p $HOME/hakios/kernel/hakios-kernel "$R/device-layer/hakios-kernel-v21.bin"
echo "-- archived kernel copy:"
sha256sum "$R/device-layer/hakios-kernel-v21.bin"
