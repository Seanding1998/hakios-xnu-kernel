#!/usr/bin/env python3
"""Wave 21.1: build the v16 cmdline from the v15 bytes.

One change, everything else byte-pinned:
  loader_return_after 300 -> 180   F6 bypass: the vnode table runs dry at ~218 s into a session
                                   (v15's 300 s window exposed it; v14's 120 s never reached it).
                                   180 keeps the whole N1->N2->N3 budget (<= 150 s) inside one
                                   session and ends it before the vnode cliff. The en0_addr boot
                                   arg and every other token stay as v15 left them.

usage: make-cmdline-v16.py CMDLINE_V15 OUT_CMDLINE_V16
"""
import sys

V15, OUT = sys.argv[1:3]

cmd = open(V15, "rb").read()
assert cmd.endswith(b"\0"), "cmdline must stay NUL-terminated"
body = cmd[:-1]
assert body.count(b"loader_return_after=300") == 1
assert body.endswith(b" root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2")

body = body.replace(b"loader_return_after=300", b"loader_return_after=180")

assert body.count(b"loader_return_after=180") == 1
assert body.endswith(b" root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2")
assert body.count(b"en0_addr=10.0.0.2") == 1
assert body.count(b"ufs_write=1") == 1 and body.count(b"var_hfs=ufs_darwin_data") == 1
assert body.count(b"root_apfs=ufs_darwin") == 1 and body.count(b"ufs=2") == 1
assert body.count(b"hw_target=D22ap") == 1 and body.count(b"ufs_check") == 0

for token in (b"serial=0", b"small_cores_after=0", b"touchscreen=1", b"buttons=1",
              b"cpus=8", b"bootcpu=7", b"soc_rsc=0x17a20000", b"soc_ipa_fw=ipa_fws"):
    assert body.count(token) == 1, token

# budget: the loader prepends "debug=0x8 " (10) + "rd=md0 " (7) + "hv_wdt_pet=1 " (13)
# + "ufs_shared_pa=0xXXXXXXXXXXXXXXXX " (33) + "hakios_kver=2.1.13-... " (59).
RESERVE = 10 + 7 + 13 + 33 + 59
BOOT_LINE_LENGTH = 608
assert len(body) + RESERVE < BOOT_LINE_LENGTH, f"cmdline too long: {len(body)}+{RESERVE}"

open(OUT, "wb").write(body + b"\0")
print(f"v15 cmdline {len(cmd)-1} B -> v16 cmdline {len(body)} B")
print("changes: loader_return_after 300->180 (F6 vnode-cliff bypass); all else byte-pinned")
print(f"budget: {len(body)}+{RESERVE} = {len(body)+RESERVE} < {BOOT_LINE_LENGTH}")
