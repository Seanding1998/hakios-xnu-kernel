#!/usr/bin/env python3
"""Wave 18 (S3-S8): build the v12 cmdline from the v11 payload's cmdline entry
(the v11 bytes, Boot #22).

Three appended tokens before the trailing NUL:
  ufs_write=1               the loader serves writes to darwin (loader.c
                            block_write_requested) and the kernel opens the
                            write path (hakios.ufs.c: /dev/rufs_darwin takes
                            writes past UFS_WRITE_FIRST=2042368);
  var_hfs=ufs_darwin_data   userland init mounts the HFS+ volume of darwin
                            blocks 2042368.. on /private/var (init.c
                            mount_data_volume) -- present even though this
                            boot's process 1 is the wave-11 stub (the arg is
                            inert until a real init runs);
  ufs_check=1               the kernel hashes the 8 reference partitions 40 s
                            in (FNV-1a, 64-bit) for the R1 (DALSYSDxe cache
                            coherence) comparison.

usage: make-cmdline-v12.py PAYLOAD_V11 OUT_CMDLINE_V12
"""
import struct, sys

V11, OUT = sys.argv[1:3]

def parse(data):
    magic, size = struct.unpack_from('<II', data, 0)
    assert magic == 0x50554E58, hex(magic)
    off = 8
    entries = {}
    while off < 8 + size:
        name, esize, _r = struct.unpack_from('<16sII', data, off)
        name = name.rstrip(b'\0').decode()
        off += 24
        if name == '':
            break
        entries[name] = data[off:off + esize]
        off += esize + (-esize % 16)
    return entries

v11 = parse(open(V11, 'rb').read())
cmd = v11['cmdline']

assert cmd.endswith(b'\0'), 'cmdline must stay NUL-terminated'
assert cmd.endswith(b' ufs=2\0'), 'v11 cmdline must end with ufs=2'
assert cmd.count(b'ufs_write') == 0 and cmd.count(b'var_hfs') == 0
assert cmd.count(b'ufs_check') == 0 and cmd.count(b'ufs_native') == 0

NEW = b' ufs_write=1 var_hfs=ufs_darwin_data ufs_check=1'
body = cmd[:-1] + NEW + b'\0'

# every byte before the appended tokens is untouched
assert body.startswith(cmd[:-1] + b' '), 'prefix must be the v11 bytes verbatim'
assert body.count(b'ufs=2') == 1
assert body.count(b'ufs_write=1') == 1
assert body.count(b'var_hfs=ufs_darwin_data') == 1
assert body.count(b'ufs_check=1') == 1
assert body.endswith(b'\0')
assert b'ufs_native' not in body

# the whole v10/v11 family must still be there, byte-for-byte
for token in (b'serial=0', b'loader_return_after=60', b'small_cores_after=0',
              b'touchscreen=1', b'buttons=1', b'buttons_map=1',
              b'buttons_core=0xc400000', b'buttons_cnfg=0xc42d000',
              b'buttons_obs=0xc440000', b'cpus=8', b'bootcpu=7',
              b'soc_ipa_base=0x3e40000', b'soc_gsi_base=0x3e04000',
              b'soc_ipcc=0xed18000', b'soc_rsc=0x17a20000',
              b'soc_mpss_mem=0x8bc00000', b'modem_ipa_fw_at=0x8b910000',
              b'soc_ipa_stream=0x5c0', b'soc_ipa_stream_uc=0x5c2',
              b'soc_ipa_fw=ipa_fws'):
    assert body.count(token) == 1, token

# loader budget (loader.c BOOT_LINE_LENGTH=608; loader prepends debug=0x8 + hakios_kver)
BOOT_LINE_LENGTH = 608
RESERVE = 10 + 58
assert len(body) - 1 + RESERVE < BOOT_LINE_LENGTH, f'cmdline too long: {len(body)-1}+{RESERVE}'

open(OUT, 'wb').write(body)
print(f'v11 cmdline {len(cmd)} B -> v12 cmdline {len(body)} B (only "{NEW.decode()}" appended)')
print(f'budget: {len(body)-1}+{RESERVE} = {len(body)-1+RESERVE} < {BOOT_LINE_LENGTH}')
print(body.decode().rstrip('\0'))
