#!/usr/bin/env python3
"""Wave 12a: repack the XNUP payload for the v10 kernel (first flash of the
s_ahb-nonfatal + GENI-probe + bitbang-fallback build).

Base = the v9 payload (Boot #16, byte-for-byte the image currently in boot_b).
Only two entries change: kernel -> hakios-kernel-v10.bin, cmdline -> the v10
cmdline (loader_return_after flipped 300->60). loader.efi / ramdisk /
kernel.ver are asserted byte-equal to the v9 entries (all three are still the
v6-era bytes: 66c6b342 / 4f72da61 / afd473f5).

XNUP format (mkpayload.py): header u32 magic "XNUP" + u32 size; entries of
char name[16], u32 size, u32 reserved, data padded to 16; terminated by an
entry whose name is empty.

usage: repack-payload-v10.py V9_PAYLOAD KERNEL_V10 CMDLINE_V10 OUT_PAYLOAD_V10
"""
import struct, sys, hashlib

V9, KERNEL, CMDLINE, OUT = sys.argv[1:5]

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

def sha(b): return hashlib.sha256(b).hexdigest()

v9 = parse(open(V9, 'rb').read())
ker = open(KERNEL, 'rb').read()
cmd = open(CMDLINE, 'rb').read()

names = [n for n, _ in v9]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v9 = Boot #16 bytes; loader/ramdisk/kernel.ver also = v6 era)
old = dict(v9)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert sha(old['kernel']).startswith('f56468c2'), sha(old['kernel'])

# kernel: the wave12a hand-off build, different from the v9 kernel
assert sha(ker).startswith('75e2a481'), sha(ker)
assert ker != old['kernel']

# cmdline: only the 300->60 flip vs the v9 entry
assert cmd != old['cmdline']
assert cmd.replace(b'loader_return_after=60', b'loader_return_after=300') == old['cmdline']

out_entries = []
for name, data in v9:
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
        assert cd == old[n], f'{n} changed unexpectedly'
assert dict(check)['kernel'] == ker
assert dict(check)['cmdline'] == cmd
assert dict(check)['ramdisk'] == old['ramdisk']
assert dict(check)['loader.efi'] == old['loader.efi']
assert dict(check)['kernel.ver'] == old['kernel.ver']
for n, d in check:
    print(f'{n:12s} {len(d):10d}  {sha(d)[:16]}')
print('v10 payload OK: only kernel+cmdline differ from v9')
