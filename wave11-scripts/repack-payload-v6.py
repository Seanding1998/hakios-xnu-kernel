#!/usr/bin/env python3
"""Repack the XNUP payload for wave 11 (v6): swap the ramdisk and cmdline
entries of the v5 payload, keep every other entry byte-for-byte, in the same
order.

XNUP format (mkpayload.py):
  header : u32 magic "XNUP", u32 size (bytes after the header)
  entries: char name[16], u32 size, u32 reserved, data padded to 16 bytes
  end    : an entry whose name is empty

usage: repack-payload-v6.py V5_PAYLOAD NEW_RAMDISK NEW_CMDLINE OUT_PAYLOAD
"""
import struct, sys

V5, RAMDISK, CMDLINE, OUT = sys.argv[1:5]

def parse(data):
    magic, size = struct.unpack_from('<II', data, 0)
    assert magic == 0x50554E58, hex(magic)
    off = 8
    end = 8 + size
    entries = []
    while off < end:
        name, esize, _rsv = struct.unpack_from('<16sII', data, off)
        name = name.rstrip(b'\0').decode()
        off += 24
        if name == '':
            break
        entries.append((name, data[off:off + esize]))
        off += esize + (-esize % 16)
    assert off == end, f'trailing bytes: off {off} != end {end}'
    return entries

def emit(out, entries):
    body = b''
    for name, data in entries:
        body += struct.pack('<16sII', name.encode(), len(data), 0) + data + b'\0' * (-len(data) % 16)
    body += b'\0' * 24
    out.write(struct.pack('<II', 0x50554E58, len(body)) + body)

v5 = parse(open(V5, 'rb').read())
ram = open(RAMDISK, 'rb').read()
cmd = open(CMDLINE, 'rb').read()          # already NUL-terminated bytes

names = [n for n, _ in v5]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

out_entries = []
for name, data in v5:
    if name == 'ramdisk':
        out_entries.append((name, ram))
    elif name == 'cmdline':
        out_entries.append((name, cmd))
    else:
        out_entries.append((name, data))

with open(OUT, 'wb') as f:
    emit(f, out_entries)

# readback: walk the new file and byte-compare against intent
check = parse(open(OUT, 'rb').read())
assert [n for n, _ in check] == names
for (n, d), (cn, cd) in zip(out_entries, check):
    assert n == cn and d == cd, n
    if n not in ('ramdisk', 'cmdline'):
        old = dict(v5)[n]
        assert cd == old, f'{n} changed unexpectedly'
assert dict(check)['cmdline'] == cmd
assert dict(check)['ramdisk'] == ram
for n, d in check:
    print(f'{n:12s} {len(d):10d}')
print('v6 payload OK: only ramdisk+cmdline differ from v5')
