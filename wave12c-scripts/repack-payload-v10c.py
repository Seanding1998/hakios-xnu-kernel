#!/usr/bin/env python3
"""Wave 12c: repack the XNUP payload for the v10c kernel (the electrical-layer
experiments build: raw-byte forensics in the v1 window and the v2 headers,
the loopback probe, and the boot-arg-gated sweep -- MISO bias, CLK pacing,
reset polarity, load-switch level).

Base = the v10b payload (Boot #18, byte-for-byte). Only the kernel entry
changes: -> hakios-kernel-v10c.bin. The cmdline is the SAME v10 bytes as
v10b's (loader_return_after=60 touchscreen=1 buttons=1 small_cores_after=0,
no new boot-args: the experiments run by default in the sweep, the boot-args
are there for v10d to steer without a rebuild). loader.efi / ramdisk /
kernel.ver are asserted byte-equal to the v10b/v9 entries (66c6b342 /
4f72da61 / afd473f5).

usage: repack-payload-v10c.py PAYLOAD_V10B KERNEL_V10C KERNEL_V10B CMDLINE_V10 OUT_PAYLOAD_V10C
"""
import struct, sys, hashlib

V10B, KERNEL, KERNEL_V10B, CMDLINE, OUT = sys.argv[1:6]

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

v10b = parse(open(V10B, 'rb').read())
ker = open(KERNEL, 'rb').read()
ker_v10b = open(KERNEL_V10B, 'rb').read()
cmd = open(CMDLINE, 'rb').read()

names = [n for n, _ in v10b]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v10b = Boot #18 bytes = v9/v6 era for these three)
old = dict(v10b)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert sha(old['kernel']).startswith('e56f989b'), sha(old['kernel'])

# kernel: the wave12c build -- different from the v10b kernel and carrying the new strings
assert sha(ker).startswith('181bfc57'), sha(ker)
assert ker != old['kernel'], 'v10c kernel equals the v10b kernel'
for needle in (b'v1 window, read %u raw', b'loopback probe', b'experiment %u of 5'):
    assert needle in ker, f'{needle} missing from the v10c kernel'

# cmdline: byte-identical to the v10b entry (which is the v10 bytes, v9's with the 300->60 flip);
# NO new boot-args -- the experiments run by default in the sweep
assert cmd == old['cmdline'], 'cmdline is not the v10b/v10 bytes'
assert b'loader_return_after=60' in cmd and b'loader_return_after=300' not in cmd
assert b'touchscreen=1' in cmd and b'small_cores_after=0' in cmd and b'buttons=1' in cmd
assert b'touch_miso_pull' not in cmd and b'touch_sweep' not in cmd

out_entries = []
for name, data in v10b:
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
print('v10c payload OK: only kernel differs from v10b; cmdline byte-identical to v10/v10b')
