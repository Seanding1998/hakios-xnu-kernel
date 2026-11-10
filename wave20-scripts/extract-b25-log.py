#!/usr/bin/env python3
"""Wave 20: extract the b25 kernel log from the pulled logdump partition.

The logdump is the console ring the loader wrote before returning: header
survey, then the kernel log, then (on a clean return) the END OF LOG marker.
Extraction = from the first `== KERNEL LOG ==` marker through `== END OF LOG ==`
(inclusive) when present, else to the last non-zero byte; NUL padding dropped;
CRLF line endings as wave18's intel/m3-boot1/b24-kernel-log.txt.

usage: extract-b25-log.py LOGDUMP_V14 OUT_B25_KERNEL_LOG
"""
import sys

src, out = sys.argv[1:3]
d = open(src, 'rb').read()

i = d.find(b'== KERNEL LOG ==')
assert i != -1, 'no KERNEL LOG marker in the logdump'
end_marker = d.find(b'== END OF LOG ==', i)
if end_marker != -1:
    body = d[i:end_marker + len(b'== END OF LOG ==')]
else:
    nz = len(d)
    while nz and d[nz-1] == 0:
        nz -= 1
    body = d[i:nz]

body = body.replace(b'\x00', b'')
open(out, 'wb').write(body)
print(f'b25 kernel log: {len(body)} bytes from logdump offset {i}')
print(f'END OF LOG marker: {"present" if end_marker != -1 else "ABSENT (truncated window)"}')
