#!/usr/bin/env python3
"""Wave 18 (S3-S8): repack the XNUP payload for v12.

v12 is a cmdline-only build: CONFIG_UFS_WRITE / CONFIG_VAR_STORE are runtime
boot-args (docs/boot-args.md:309 `ufs_write` KL, :432 `var_store` U), not
compile gates -- the write path, the check and the saver were already compiled
into the v11 kernel (CONFIG_HAKIOS_UFS=y pulls in the whole hakios.ufs.c), and
the v5-era loader in the payload already carries the darwin write offer
(strings-check-v12.sh). `make kernel` after the two config lines produced a
byte-identical binary (sha a7f4641f...), so the kernel entry is pinned EQUAL
to v11 and only the cmdline entry changes:

  cmdline -> the v12 bytes (the v11 bytes + " ufs_write=1
             var_hfs=ufs_darwin_data ufs_check=1")
loader.efi / kernel / ramdisk / kernel.ver are asserted byte-equal to the v11
entries (66c6b342 / a7f4641f / 4f72da61 / afd473f5).

usage: repack-payload-v12.py PAYLOAD_V11 CMDLINE_V12 OUT_PAYLOAD_V12
"""
import struct, sys, hashlib

V11, CMDLINE, OUT = sys.argv[1:4]

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

v11 = parse(open(V11, 'rb').read())
cmd = open(CMDLINE, 'rb').read()

names = [n for n, _ in v11]
assert names == ['loader.efi', 'kernel', 'ramdisk', 'cmdline', 'kernel.ver'], names

# untouched-entry pins (v11 = Boot #22 bytes)
old = dict(v11)
assert sha(old['loader.efi']).startswith('66c6b342'), sha(old['loader.efi'])
assert sha(old['kernel']).startswith('a7f4641f'), sha(old['kernel'])
assert sha(old['ramdisk']).startswith('4f72da61'), sha(old['ramdisk'])
assert sha(old['kernel.ver']).startswith('afd473f5'), sha(old['kernel.ver'])
assert old['cmdline'].endswith(b' ufs=2\0'), 'v11 cmdline must end with ufs=2'

# cmdline: the v12 bytes -- v11 + the three S3-S8 tokens, nothing else
assert cmd == old['cmdline'][:-1] + b' ufs_write=1 var_hfs=ufs_darwin_data ufs_check=1\0', \
    'cmdline is not v11 + the wave-18 tokens'
assert cmd.count(b'ufs_write=1') == 1 and cmd.count(b'var_hfs=ufs_darwin_data') == 1
assert cmd.count(b'ufs_check=1') == 1 and cmd.count(b'ufs_native') == 0

out_entries = []
for name, data in v11:
    if name == 'cmdline':
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
    if n != 'cmdline':
        assert cd == old[n], f'{n} changed unexpectedly'
assert dict(check)['cmdline'] == cmd
assert dict(check)['kernel'] == old['kernel']
assert dict(check)['loader.efi'] == old['loader.efi']
assert dict(check)['ramdisk'] == old['ramdisk']
assert dict(check)['kernel.ver'] == old['kernel.ver']
for n, d in check:
    print(f'{n:12s} {len(d):10d}  {sha(d)[:16]}')
print('v12 payload OK: cmdline only; loader/kernel/ramdisk/kernel.ver byte-identical to v11')
