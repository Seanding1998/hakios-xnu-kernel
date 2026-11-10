#!/bin/bash
# Wave 22 verify wrapper: re-extracts the pinned kernel/kernel.ver from the v16 payload
# (WSL /tmp does not survive across calls), then runs verify-udon-hakios-v18.py -- all in
# one WSL session.
set -e
R=HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
TMP=/tmp/v18
mkdir -p $TMP
python3 - "$R/device-layer/udon-hakios-payload-v16.bin" <<'EOF'
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
    if name in ('kernel', 'kernel.ver'):
        open('/tmp/v18/' + name, 'wb').write(entry)
        print('extracted:', name, esize, 'bytes')
EOF
echo "-- pinned kernel (must equal v15/v16's 17c905ec):"
sha256sum $TMP/kernel | grep -q "^17c905ec" || { echo "kernel drift"; exit 1; }
python3 -I $R/wave22-scripts/verify-udon-hakios-v18.py \
  $R/device-layer/udon-hakios-grafted-v18.img \
  $R/device-layer/stock-boot-a.img \
  /home/HOST-REDACTED/hakios/uefi-udon/BootShim/BootShim.bin \
  /home/HOST-REDACTED/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd \
  $R/device-layer/udon-hakios-payload-v18.bin \
  $R/device-layer/udon-hakios-payload-v16.bin \
  $R/device-layer/udon-hakios-cmdline-v17.bin \
  $TMP/kernel
