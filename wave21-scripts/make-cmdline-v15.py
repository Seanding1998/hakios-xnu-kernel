#!/usr/bin/env python3
"""Wave 21 (loader-bridge network -> SSH): build the v15 cmdline from the v14 bytes.

Two changes, everything else byte-pinned:
  loader_return_after 120 -> 300  the SSH session is the whole point of this run: the pump,
                                  ping and login all happen inside one session, and the brief
                                  asks for 300 (the reset loop still catches a lost host).
  append " en0_addr=10.0.0.2"     en0's address on the loader's channel: this boot-arg is what
                                  turns the new link driver on (drivers/net/hakios.loader_net.c),
                                  which also sets the address, /30 mask and flags from the kernel.

usage: make-cmdline-v15.py CMDLINE_V14 OUT_CMDLINE_V15
"""
import sys

V14, OUT = sys.argv[1:3]

cmd = open(V14, "rb").read()
assert cmd.endswith(b"\0"), "cmdline must stay NUL-terminated"
body = cmd[:-1]
assert body.count(b"loader_return_after=120") == 1
assert body.endswith(b" root_apfs=ufs_darwin hw_target=D22ap")

body = body.replace(b"loader_return_after=120", b"loader_return_after=300")
body += b" en0_addr=10.0.0.2"

assert body.count(b"loader_return_after=300") == 1
assert body.endswith(b" root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2")
assert body.count(b"en0_addr=10.0.0.2") == 1
assert body.count(b"ufs_write=1") == 1 and body.count(b"var_hfs=ufs_darwin_data") == 1
assert body.count(b"root_apfs=ufs_darwin") == 1 and body.count(b"ufs=2") == 1
assert body.count(b"hw_target=D22ap") == 1 and body.count(b"ufs_check") == 0

for token in (b"serial=0", b"small_cores_after=0", b"touchscreen=1", b"buttons=1",
              b"cpus=8", b"bootcpu=7", b"soc_rsc=0x17a20000", b"soc_ipa_fw=ipa_fws"):
    assert body.count(token) == 1, token

# budget: the loader prepends "debug=0x8 " (10) + "rd=md0 " (7) + "hv_wdt_pet=1 " (13)
# + "ufs_shared_pa=0xXXXXXXXXXXXXXXXX " (33) + "hakios_kver=2.1.13-... " (59) and now also
# "net_shared..." -- nothing: the net ring rides the same page, no new boot-arg is appended.
RESERVE = 10 + 7 + 13 + 33 + 59
BOOT_LINE_LENGTH = 608
assert len(body) + RESERVE < BOOT_LINE_LENGTH, f"cmdline too long: {len(body)}+{RESERVE}"

open(OUT, "wb").write(body + b"\0")
print(f"v14 cmdline {len(cmd)-1} B -> v15 cmdline {len(body)} B")
print("changes: loader_return_after 120->300, +en0_addr=10.0.0.2")
print(f"budget: {len(body)}+{RESERVE} = {len(body)+RESERVE} < {BOOT_LINE_LENGTH}")
