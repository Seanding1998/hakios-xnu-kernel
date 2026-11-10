#!/usr/bin/env python3
"""Wave 16 (S0-S2, UFS read-only bring-up): build the v11 cmdline from the
v10e payload's cmdline entry (the v10 bytes, Boot #17-#21 family).

The only change is one appended token: ` ufs=2` before the trailing NUL. It is
parsed on both sides (loader.c block_start: ufs=2 starts the loader's block
service on core 0; hakios.ufs.c: the kernel's mailbox block/char devices). No
ufs_write / var_hfs / ufs_native args this round -- S3+ territory; native is
compiled in (CONFIG_UFS_NATIVE=y) but stays boot-arg-gated off.

usage: make-cmdline-v11.py PAYLOAD_V10E OUT_CMDLINE_V11
"""
import struct, sys

V10E, OUT = sys.argv[1:3]

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

v10e = parse(open(V10E, 'rb').read())
cmd = v10e['cmdline']

assert cmd.endswith(b'\0'), 'cmdline must stay NUL-terminated'
assert cmd.count(b'ufs=') == 0, 'v10e cmdline already carries a ufs= token'
assert cmd.count(b'ufs_write') == 0 and cmd.count(b'var_hfs') == 0
assert cmd.count(b'ufs_native') == 0

body = cmd[:-1] + b' ufs=2\0'

# every byte before the appended token is untouched
assert body == cmd[:-1] + b' ufs=2\0'
assert body.count(b'ufs=2') == 1
assert body.startswith(cmd[:-1] + b' '), 'prefix must be the v10e bytes verbatim'
assert body.endswith(b'\0')

# the whole v10 family must still be there, byte-for-byte
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
print(f'v10e cmdline {len(cmd)} B -> v11 cmdline {len(body)} B (only " ufs=2" appended)')
print(body.decode().rstrip('\0'))
