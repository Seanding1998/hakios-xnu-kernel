#!/usr/bin/env python3
"""Wave 20 (launchd alive + /jb): build the v14 cmdline from the v13 bytes.

Three changes, everything else byte-pinned:
  loader_return_after 60 -> 120   the new launchd session gets a longer window
                                  (b24 died 0.6 s after ignition took pid 1; a
                                  live launchd walks rc jobs + sshd, worth more
                                  than 60 s of observation)
  drop " ufs_check=1"             the write path was proven twice (wave18 b23
                                  16/16 FNV match; b24 S6-S8), the check only
                                  costs time and log noise
  append " hw_target=D22ap"       THE FIX: hw.target sysctl no longer answers
                                  EINVAL (kern_mib.c now takes the boot arg);
                                  the 16.5 libignition in dyld halts pid 1 on
                                  that EINVAL ("failed to query hardware
                                  target: 22"). D22ap = the iPhone X target the
                                  system volume was built from.

usage: make-cmdline-v14.py CMDLINE_V13 OUT_CMDLINE_V14
"""
import sys

V13, OUT = sys.argv[1:3]

cmd = open(V13, 'rb').read()
assert cmd.endswith(b'\0'), 'cmdline must stay NUL-terminated'
body = cmd[:-1]
assert body.count(b'loader_return_after=60') == 1
assert body.endswith(b' ufs_check=1 root_apfs=ufs_darwin')

body = body.replace(b'loader_return_after=60', b'loader_return_after=120')
body = body.replace(b' ufs_check=1', b'')
body += b' hw_target=D22ap'

assert body.count(b'loader_return_after=120') == 1
assert body.count(b'ufs_check') == 0
assert body.count(b'hw_target=D22ap') == 1
assert body.endswith(b' root_apfs=ufs_darwin hw_target=D22ap')
assert body.count(b'ufs_write=1') == 1 and body.count(b'var_hfs=ufs_darwin_data') == 1
assert body.count(b'root_apfs=ufs_darwin') == 1 and body.count(b'ufs=2') == 1

for token in (b'serial=0', b'small_cores_after=0', b'touchscreen=1', b'buttons=1',
              b'cpus=8', b'bootcpu=7', b'soc_rsc=0x17a20000', b'soc_ipa_fw=ipa_fws'):
    assert body.count(token) == 1, token

BOOT_LINE_LENGTH = 608
RESERVE = 10 + 58
assert len(body) + RESERVE < BOOT_LINE_LENGTH, f'cmdline too long: {len(body)}+{RESERVE}'

open(OUT, 'wb').write(body + b'\0')
print(f'v13 cmdline {len(cmd)-1} B -> v14 cmdline {len(body)} B')
print(f'changes: loader_return_after 60->120, -ufs_check, +hw_target=D22ap')
print(f'budget: {len(body)}+{RESERVE} = {len(body)+RESERVE} < {BOOT_LINE_LENGTH}')
