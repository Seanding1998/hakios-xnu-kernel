#!/usr/bin/env python3
"""Wave 18 (S6-S8, real-init chain): build the v13 cmdline from the v12 bytes.

One appended token before the trailing NUL:
  root_apfs=ufs_darwin     init.c flash_root(): mounts the Darwin root volume
                           (our system.apfs, darwin block 0) as the root, then
                           mount_writable() runs either way; with
                           var_hfs=ufs_darwin_data the HFS+ data volume mounts
                           on /private/var (the S6/S7/S8 acceptance lines).

usage: make-cmdline-v13.py CMDLINE_V12 OUT_CMDLINE_V13
"""
import sys

V12, OUT = sys.argv[1:3]

cmd = open(V12, 'rb').read()
assert cmd.endswith(b'\0'), 'cmdline must stay NUL-terminated'
assert cmd.endswith(b' ufs_check=1\0'), 'v12 cmdline must end with ufs_check=1'
assert cmd.count(b'root_apfs') == 0

NEW = b' root_apfs=ufs_darwin'
body = cmd[:-1] + NEW + b'\0'

assert body.startswith(cmd[:-1] + b' '), 'prefix must be the v12 bytes verbatim'
assert body.count(b'root_apfs=ufs_darwin') == 1
assert body.count(b'ufs_write=1') == 1 and body.count(b'var_hfs=ufs_darwin_data') == 1
assert body.count(b'ufs_check=1') == 1 and body.count(b'ufs=2') == 1
assert body.endswith(b'\0') and b'ufs_native' not in body

for token in (b'serial=0', b'loader_return_after=60', b'small_cores_after=0',
              b'touchscreen=1', b'buttons=1', b'cpus=8', b'bootcpu=7',
              b'soc_rsc=0x17a20000', b'soc_ipa_fw=ipa_fws'):
    assert body.count(token) == 1, token

BOOT_LINE_LENGTH = 608
RESERVE = 10 + 58
assert len(body) - 1 + RESERVE < BOOT_LINE_LENGTH, f'cmdline too long: {len(body)-1}+{RESERVE}'

open(OUT, 'wb').write(body)
print(f'v12 cmdline {len(cmd)} B -> v13 cmdline {len(body)} B (only "{NEW.decode()}" appended)')
print(f'budget: {len(body)-1}+{RESERVE} = {len(body)-1+RESERVE} < {BOOT_LINE_LENGTH}')
print(body.decode().rstrip('\0'))
