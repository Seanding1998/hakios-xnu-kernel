#!/usr/bin/env python3
"""Wave 16 (S0-S2): repack the XNUP payload for the v11 kernel (the UFS
read-only bring-up build: CONFIG_HAKIOS_UFS=y + CONFIG_UFS_NATIVE=y compiled
in, mailbox block service activated by the new `ufs=2` boot-arg; no write
path this round -- CONFIG_UFS_WRITE stays off).

Base = the v10e payload (Boot #21, byte-for-byte). Two entries change:
  - kernel  -> hakios-kernel-v11.bin (the incremental rebuild)
  - cmdline -> the v11 cmdline (the v10e bytes + " ufs=2")
loader.efi / ramdisk / kernel.ver are asserted byte-equal to the v10e entries
(66c6b342 / 4f72da61 / afd473f5 -- the v5/v6-era untouched builds).

usage: repack-payload-v11.py PAYLOAD_V10E KERNEL_V11 CMDLINE_V11 OUT_PAYLOAD_V11
"""
import struct, sys, hashlib

V10E, KERNEL, CMDLINE, OUT = sys.argv[1:5]

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

v10e = parse(open(V10E, 'rb').read())
ker = open(KERNEL, 'rb').read()
cmd = open(CMDLINE, 'rb').read()

names = [n for n, _ in v10e]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v10e = Boot #21 bytes; loader/ramdisk/kernel.ver = v5/v6 era)
old = dict(v10e)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert sha(old['kernel']).startswith('b777ff5d'), sha(old['kernel'])  # v10e kernel

# kernel: the v11 build -- different from the v10e kernel and carrying the UFS strings
assert ker != old['kernel'], 'v11 kernel equals the v10e kernel'
for needle in (b'ufs: no node for', b'partitions of the phone', b'ufs_requests'):
    assert needle in ker, f'{needle} missing from the v11 kernel'

# cmdline: the v11 bytes -- v10e + " ufs=2", nothing else
assert cmd == old['cmdline'][:-1] + b' ufs=2\0', 'cmdline is not v10e + ufs=2'
assert cmd.count(b'ufs=2') == 1
assert b'ufs_write' not in cmd and b'var_hfs' not in cmd and b'ufs_native' not in cmd
assert b'loader_return_after=60' in cmd and b'loader_return_after=300' not in cmd
assert b'touchscreen=1' in cmd and b'small_cores_after=0' in cmd and b'buttons=1' in cmd

out_entries = []
for name, data in v10e:
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
print('v11 payload OK: kernel + cmdline differ from v10e; loader/ramdisk/kernel.ver byte-identical')
