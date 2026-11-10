#!/usr/bin/env python3
"""Wave 12a: build the v10 cmdline from the v9 payload's cmdline entry.

The only change is loader_return_after=300 -> loader_return_after=60 (the TCM
probe finishes inside the kernel's first ~15 s, so a 60 s session is plenty for
evidence while cutting the ABL fallback loop to ~10 minutes). Every other byte
stays identical to the v9 cmdline.

usage: make-cmdline-v10.py V9_PAYLOAD OUT_CMDLINE_V10
"""
import struct, sys

V9, OUT = sys.argv[1:3]

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

v9 = parse(open(V9, 'rb').read())
cmd9 = v9['cmdline']

OLD = b'loader_return_after=300'
NEW = b'loader_return_after=60'
assert cmd9.count(OLD) == 1, 'v9 cmdline must carry loader_return_after=300 exactly once'
cmd10 = cmd9.replace(OLD, NEW)

# every byte outside the flipped token is untouched
assert cmd10 == cmd9[:cmd9.index(OLD)] + NEW + cmd9[cmd9.index(OLD) + len(OLD):]
assert cmd10.count(b'loader_return_after=60') == 1
assert cmd10.count(b'loader_return_after=300') == 0
assert cmd10.count(b'loader_return_after=20') == 0
assert cmd10.endswith(b'\0'), 'cmdline must stay NUL-terminated'
# the whole wave-12/v9 family must still be there, byte-for-byte
for token in (b'serial=0', b'small_cores_after=0', b'touchscreen=1', b'buttons=1',
              b'buttons_map=1', b'buttons_core=0xc400000', b'buttons_cnfg=0xc42d000',
              b'buttons_obs=0xc440000', b'cpus=8', b'bootcpu=7',
              b'soc_ipa_base=0x3e40000', b'soc_gsi_base=0x3e04000',
              b'soc_ipcc=0xed18000', b'soc_rsc=0x17a20000',
              b'soc_mpss_mem=0x8bc00000', b'modem_ipa_fw_at=0x8b910000',
              b'soc_ipa_stream=0x5c0', b'soc_ipa_stream_uc=0x5c2',
              b'soc_ipa_fw=ipa_fws'):
    assert cmd10.count(token) == 1, token

# loader budget (loader.c BOOT_LINE_LENGTH=608; loader prepends debug=0x8 + hakios_kver)
BOOT_LINE_LENGTH = 608
RESERVE = 10 + 58
assert len(cmd10) - 1 + RESERVE < BOOT_LINE_LENGTH, f'cmdline too long: {len(cmd10)-1}+{RESERVE}'

open(OUT, 'wb').write(cmd10)
print(f'v9 cmdline {len(cmd9)} B -> v10 cmdline {len(cmd10)} B (only 300->60 flipped)')
print(cmd10.decode().rstrip('\0'))
