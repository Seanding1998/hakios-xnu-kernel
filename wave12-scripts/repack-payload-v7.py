#!/usr/bin/env python3
"""Repack the XNUP payload for wave 12 (v7): swap the kernel and cmdline entries of the
v6 payload, keep every other entry byte-for-byte, in the same order.

XNUP format (mkpayload.py):
  header : u32 magic "XNUP", u32 size (bytes after the header)
  entries: char name[16], u32 size, u32 reserved, data padded to 16 bytes
  end    : an entry whose name is empty

usage: repack-payload-v7.py V6_PAYLOAD NEW_KERNEL NEW_CMDLINE OUT_PAYLOAD
"""
import struct, sys

V6, KERNEL, CMDLINE, OUT = sys.argv[1:5]

BOOT_LINE_LENGTH = 608          # loader.c: the kernel's boot_args capacity; the loader adds
                                # "debug=0x8 " and hakios_kver=... before the payload's cmdline
RESERVE = 10 + 58               # debug=0x8 + hakios_kver=2.1.13-hakios-darwin22.5-sm8475-g96ffbc53-dirty + space

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

v6 = parse(open(V6, 'rb').read())
ker = open(KERNEL, 'rb').read()
cmd = open(CMDLINE, 'rb').read()          # already NUL-terminated bytes

assert cmd[-1:] == b'\0', 'cmdline must be NUL-terminated'
assert len(cmd) - 1 + RESERVE < BOOT_LINE_LENGTH, f'cmdline too long for the kernel: {len(cmd) - 1}+{RESERVE} >= {BOOT_LINE_LENGTH}'
assert cmd.count(b'loader_return_after=300') == 1, 'loader_return_after=300 expected'
assert cmd.count(b'small_cores_after=0') == 1, 'small_cores_after=0 expected'
assert cmd.count(b'touchscreen=1') == 1, 'touchscreen=1 expected'
assert cmd.count(b'buttons=1') == 1 and cmd.count(b'buttons_map=1') == 1, 'buttons args expected'
assert cmd.count(b'loader_return_after=60') == 0, 'the v6 value must be gone'

names = [n for n, _ in v6]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

out_entries = []
for name, data in v6:
    if name == 'kernel':
        out_entries.append((name, ker))
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
    if n not in ('kernel', 'cmdline'):
        old = dict(v6)[n]
        assert cd == old, f'{n} changed unexpectedly'
assert dict(check)['cmdline'] == cmd
assert dict(check)['kernel'] == ker
assert dict(check)['ramdisk'] == dict(v6)['ramdisk']
assert dict(check)['loader.efi'] == dict(v6)['loader.efi']
assert dict(check)['kernel.ver'] == dict(v6)['kernel.ver']
for n, d in check:
    print(f'{n:12s} {len(d):10d}')
print('v7 payload OK: only kernel+cmdline differ from v6')
