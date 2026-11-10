#!/usr/bin/env python3
"""Wave 12b: repack the XNUP payload for the v10b kernel (the probe-verdict
build: one line changed against v10 -- v1_read goes through spi_xfer so the
bitbang fallback actually answers the v1 window).

Base = the v9 payload (Boot #16, byte-for-byte; the same base wave12a used).
Two entries change: kernel -> hakios-kernel-v10b.bin, cmdline -> the SAME v10
cmdline bytes (loader_return_after=60 touchscreen=1 buttons=1
small_cores_after=0 -- wave12b changes nothing on the command line).
loader.efi / ramdisk / kernel.ver are asserted byte-equal to the v9 entries
(66c6b342 / 4f72da61 / afd473f5, the untouched v6-era bytes).

usage: repack-payload-v10b.py V9_PAYLOAD KERNEL_V10B CMDLINE_V10 KERNEL_V10 EXPECTED_KERNEL_V10B_SHA_PREFIX OUT_PAYLOAD_V10B
"""
import struct, sys, hashlib

V9, KERNEL, CMDLINE, KERNEL_V10, PREFIX, OUT = sys.argv[1:7]

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
ker_v10 = open(KERNEL_V10, 'rb').read()

names = [n for n, _ in v9]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v9 = Boot #16 bytes; loader/ramdisk/kernel.ver also = v6 era)
old = dict(v9)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert sha(old['kernel']).startswith('f56468c2'), sha(old['kernel'])

# kernel: the wave12b build -- different from both the v9 kernel and the v10 kernel
assert sha(ker).startswith(PREFIX), sha(ker)
assert ker != old['kernel'], 'v10b kernel equals the v9 kernel'
assert ker != ker_v10, 'v10b kernel equals the v10 kernel'

# cmdline: byte-identical to the v10 cmdline (which is v9's with the 300->60 flip)
assert cmd == cmd.replace(b'loader_return_after=60', b'loader_return_after=300').replace(
    b'loader_return_after=300', b'loader_return_after=60'), 'cmdline sanity'
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
print('v10b payload OK: only kernel differs from v10/v9; cmdline is the v10 bytes')
