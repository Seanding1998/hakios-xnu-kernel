#!/bin/bash
# Wave 24 (Exp-1 diagnostic) payload: the v18 payload with the loader swapped for the
# Wave 24 diagnostic build and the cmdline kept at the v18 bytes (the 180 s short-session
# baseline, en0_addr in -- the largest proven baseline; the USB diagnosis shares nothing
# with the display experiments). Kernel/resident/ramdisk/kernel.ver/usb are the v18
# payload's entries byte for byte.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v24
mkdir -p $TMP

echo "-- extract the v18 payload's entries (the pin sources):"
python3 - "$R/device-layer/udon-hakios-payload-v18.bin" <<'EOF'
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
    open('/tmp/v24/' + name, 'wb').write(entry)
    print('carried over:', name, esize, 'bytes')
EOF

echo "-- v24 payload build (loader swapped, all else pinned to the v18 payload):"
cd ~/hakios/kernel/xnuloader
python3 mkpayload.py -o "$R/device-layer/udon-hakios-payload-v24.bin" \
  --usb \
  loader.efi=$HOME/hakios/kernel/xnuloader/loader.efi \
  kernel=/tmp/v24/kernel \
  resident=/tmp/v24/resident \
  ramdisk=/tmp/v24/ramdisk \
  cmdline=/tmp/v24/cmdline \
  kernel.ver=/tmp/v24/kernel.ver \
  --no-version

python3 - "$R/device-layer/udon-hakios-payload-v24.bin" "$R/device-layer/udon-hakios-payload-v18.bin" "$R/device-layer/udon-hakios-cmdline-v17.bin" <<'EOF'
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

v24 = entries(sys.argv[1])
v18 = entries(sys.argv[2])
cmdfile = open(sys.argv[3], 'rb').read()
assert sorted(v24) == ['cmdline', 'kernel', 'kernel.ver', 'loader.efi', 'ramdisk', 'resident', 'usb'], sorted(v24)
for name in ('kernel', 'kernel.ver', 'cmdline', 'resident', 'ramdisk', 'usb'):
    assert v24[name] == v18[name], f'{name} drifted from the v18 payload entry'
assert v24['cmdline'] == cmdfile, 'cmdline is not the v17/v18 file bytes'
assert b'loader_return_after=180' in v24['cmdline'] and b'en0_addr=10.0.0.2' in v24['cmdline']
assert b'rec_secs' not in v24['cmdline'], 'the recording boot-args must stay out of the USB diagnosis'
lh = hashlib.sha256(v24['loader.efi']).hexdigest()
l = v24['loader.efi']
# the Wave 24 loader, by its own marks:
for s in (b'checkpoint-1: the standing receive is in',
          b'checkpoint-3: the standing receive finished',
          b'SerialPort Lib',
          b'the console mirror: vendor door',
          b'the bring-up begins (the Wave 24 timeline runs from here)',
          b'sample %s (vendor): speed %d',
          b'refused %x again',
          b'the first refusal is on the record',
          b'soft reset was still set after the wait: cleared by hand',
          b'the raw UsbFn look (gen %d, a second submit by design)',
          b'the receive buffer alone (%x)',
          b'a second submit by design'):
    assert s in l, f'v24 loader missing {s}'
assert b'bulk probe gen %d beat %d: %x (wrapped)' not in l, 'the v19b beat-0 raw look must be retired'
assert b'the zero-length probe' not in l, 'the zero-length probe must be retired'
import struct as st
found = None
for m in range(0, len(l) - 40, 4):
    if st.unpack_from('<I', l, m)[0] == 0x52BE8008:      # movz w?, #0xF400, lsl #16
        for k in (1, 2, 3, 4, 5, 6):
            if st.unpack_from('<I', l, m + 4 * k)[0] == 0x72AA0AB3:   # movk w?, #0x5055, lsl #16
                found = (m, k)
                break
        if found:
            break
assert found, 'PAYLOAD_BASE pin: no movz #0xF400 near the XNUP magic movk'
print(f"loader.efi {lh[:16]} (Wave 24 diagnostic: mirror + pump + standing RX + gate + sampler)")
print(f"PAYLOAD_BASE pin: movz #0xF400 at {hex(found[0])}, the XNUP movk {k * 4} bytes later")
print('kernel/cmdline/resident/ramdisk/kernel.ver/usb == v18 payload entries byte-for-byte')
assert sum(len(v) for v in v24.values()) < 0x4000000 - 0x1000, 'payload over the 64 MB window'
EOF

echo "-- payload v24:"
sha256sum "$R/device-layer/udon-hakios-payload-v24.bin"
ls -la "$R/device-layer/udon-hakios-payload-v24.bin"
