#!/usr/bin/env python3
"""Extract the entries of an XNUP payload (Wave 10 helper).

usage: extract-entries.py PAYLOAD.bin OUTDIR [NAME...]

Writes OUTDIR/<name> for every entry (or the named ones) and prints
name/size/sha256 lines.
"""
import hashlib, os, struct, sys

PAYLOAD, OUTDIR = sys.argv[1], sys.argv[2]
WANT = sys.argv[3:]

data = open(PAYLOAD, 'rb').read()
magic, size = struct.unpack_from('<II', data, 0)
assert magic == 0x50554e58, hex(magic)          # "XNUP"
off = 8
while True:
    name, esize, _rsv = struct.unpack_from('<16sII', data, off)
    name = name.rstrip(b'\0').decode()
    off += 24
    body = data[off:off + esize]
    off += esize + (-esize % 16)
    if name == '':
        break
    if WANT and name not in WANT:
        continue
    with open(os.path.join(OUTDIR, name), 'wb') as f:
        f.write(body)
    print(f'{name:12s} {esize:10d}  sha256 {hashlib.sha256(body).hexdigest()}')
