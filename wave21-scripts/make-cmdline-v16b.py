#!/usr/bin/env python3
"""Wave 21.2: the v16b cmdline is the v16 cmdline, byte for byte.

The construction order (wave21_1 §6 item 2) changes only the loader: no boot-arg moves. The
180 s session window stays (the F6 vnode-cliff bypass that v16 proved on device), en0_addr
stays, and the budget line stays inside 608.

usage: make-cmdline-v16b.py CMDLINE_V16 OUT_CMDLINE_V16B
"""
import hashlib
import sys

V16, OUT = sys.argv[1:3]

cmd = open(V16, "rb").read()
assert cmd.endswith(b"\0"), "cmdline must stay NUL-terminated"
body = cmd[:-1]

# the v16 shape, pinned again here so a drifted source cannot slip through
assert body.count(b"loader_return_after=180") == 1
assert body.endswith(b" root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2")
assert body.count(b"en0_addr=10.0.0.2") == 1
assert body.count(b"ufs_write=1") == 1 and body.count(b"var_hfs=ufs_darwin_data") == 1
assert body.count(b"root_apfs=ufs_darwin") == 1 and body.count(b"ufs=2") == 1
assert body.count(b"hw_target=D22ap") == 1 and body.count(b"ufs_check") == 0
for token in (b"serial=0", b"small_cores_after=0", b"touchscreen=1", b"buttons=1",
              b"cpus=8", b"bootcpu=7", b"soc_rsc=0x17a20000", b"soc_ipa_fw=ipa_fws"):
    assert body.count(token) == 1, token

RESERVE = 10 + 7 + 13 + 33 + 59          # debug/rd/hv_wdt_pet/ufs_shared_pa/hakios_kver, prepended by the loader
BOOT_LINE_LENGTH = 608
assert len(body) + RESERVE < BOOT_LINE_LENGTH, f"cmdline too long: {len(body)}+{RESERVE}"

open(OUT, "wb").write(body + b"\0")
same = open(OUT, "rb").read() == cmd
print(f"v16 cmdline {len(cmd)-1} B -> v16b cmdline {len(body)} B (byte-identical: {same})")
print(f"sha256: {hashlib.sha256(open(OUT,'rb').read()).hexdigest()[:16]}")
print(f"budget: {len(body)}+{RESERVE} = {len(body)+RESERVE} < {BOOT_LINE_LENGTH}")
assert same, "the copy diverged from its source"
