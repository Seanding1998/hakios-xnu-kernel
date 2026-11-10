#!/usr/bin/env python3
"""Wave 12c fix 2: repack the XNUP payload for the v10d kernel (the v10
chunk-harvest build: v1_read fetches message continuations in nine-byte
frames, which is what Boot #19's forensics show the chip delivers, instead
of one long frame whose padding was then checked at the wrong index).

Base = the v10c payload (Boot #19, byte-for-byte). Only the kernel entry
changes: -> hakios-kernel-v10d.bin. The cmdline stays the v10 bytes (the
v10b/v10c bytes; no boot-args -- the sweep and the experiments are default-on
in the driver). loader.efi / ramdisk / kernel.ver are asserted byte-equal to
the v10c entries (66c6b342 / 4f72da61 / afd473f5).

usage: repack-payload-v10d.py PAYLOAD_V10C KERNEL_V10D KERNEL_V10C CMDLINE_V10 OUT_PAYLOAD_V10D
"""
import struct, sys, hashlib

V10C, KERNEL, KERNEL_V10C, CMDLINE, OUT = sys.argv[1:6]

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

v10c = parse(open(V10C, 'rb').read())
ker = open(KERNEL, 'rb').read()
ker_v10c = open(KERNEL_V10C, 'rb').read()
cmd = open(CMDLINE, 'rb').read()

names = [n for n, _ in v10c]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v10c = Boot #19 bytes; loader/ramdisk/kernel.ver = v9/v6 era)
old = dict(v10c)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert sha(old['kernel']).startswith('181bfc57'), sha(old['kernel'])

# kernel: the v10d build -- different from the v10c kernel and carrying the chunk strings
assert sha(ker).startswith('49268c95'), sha(ker)
assert ker != old['kernel'], 'v10d kernel equals the v10c kernel'
for needle in (b'v1 chunk %u:', b'loopback probe', b'experiment %u of 5'):
    assert needle in ker, f'{needle} missing from the v10d kernel'

# cmdline: byte-identical to the v10b/v10c entry (the v10 bytes); NO new boot-args
assert cmd == old['cmdline'], 'cmdline is not the v10c/v10 bytes'
assert b'loader_return_after=60' in cmd and b'loader_return_after=300' not in cmd
assert b'touchscreen=1' in cmd and b'small_cores_after=0' in cmd and b'buttons=1' in cmd
assert b'touch_miso_pull' not in cmd and b'touch_sweep' not in cmd

out_entries = []
for name, data in v10c:
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
assert dict(check)['cmdline'] == cmd == old['cmdline']
assert dict(check)['ramdisk'] == old['ramdisk']
assert dict(check)['loader.efi'] == old['loader.efi']
assert dict(check)['kernel.ver'] == old['kernel.ver']
for n, d in check:
    print(f'{n:12s} {len(d):10d}  {sha(d)[:16]}')
print('v10d payload OK: only kernel differs from v10c; cmdline byte-identical to v10/v10b/v10c')
