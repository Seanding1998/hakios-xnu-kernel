#!/usr/bin/env python3
"""Wave 23 cmdline v19 builder: the virtual-display evidence round (cmdline-only).

v19 = the v17/v18 bytes with exactly three edits (T1 verdict, docs/research/f13-virtual-display.md):
  1. loader_return_after 180 -> 300 (b25's 120 s was not enough for SpringBoard; upstream QEMU
     shows the home screen at about five minutes; the recording needs the long window);
  2. " en0_addr=10.0.0.2" dropped (budget, see below: the en0 driver only starts WITH this arg
     -- drivers/net/hakios.loader_net.c:11 -- and this wave's serving channel is the loader's
     own USB bulk command server, which needs no IP; restored in a later wave if wanted);
  3. " rec_secs=280 rec_ring=1 rec_mb=256" appended (MiniIOMobileFramebuffer.cpp:118-142:
     rec_secs/rec_start/rec_mb/rec_ring/rec_step; 256 MB is the upstream-proven safe size --
     640 MB had Darwin killing SpringBoard and the window server; rec_ring keeps the LAST
     frames so the run's end -- the home screen -- is what the recording holds).

The budget is NOT 607 characters of payload cmdline: the loader composes the kernel's
BOOT_LINE_LENGTH-1=607 field as a 110-character head ("debug=0x8 rd=md0 ufs_shared_pa=0x<NX16>
hakios_kver=<47> ", loader.c:3368-3452) plus the payload's own cmdline, truncating the tail
with a WARNING if over. Ground truth: logdump-v18.bin @83231 holds a v15-era composed line of
exactly 581 = 110 + 471 characters. The f13 estimate ("228 characters spare") counted the
payload line only. v18's real headroom was 26 characters -- the full f13 append (105) would
have truncated. v19: 488 payload characters -> 598 of 607 composed.

usage: make-cmdline-v19.py CMDLINE_V17_BIN OUT_BIN
"""
import hashlib
import sys

src, out = sys.argv[1:3]

raw = open(src, "rb").read()
s = raw.rstrip(b"\0").decode("ascii")
assert len(s) == 471, "v17/v18 payload cmdline is 471 characters, got %d" % len(s)
assert raw.endswith(b"\0"), "cmdline file must be NUL-terminated"

s19 = s.replace("loader_return_after=180", "loader_return_after=300")
assert s19 != s, "loader_return_after=180 not found"

assert s19.endswith(" en0_addr=10.0.0.2"), "unexpected tail"
s19 = s19[: -len(" en0_addr=10.0.0.2")]

s19 += " rec_secs=280 rec_ring=1 rec_mb=256"

# --- budget arithmetic (the T1 finding) ---
HEAD_MEASURED = 110          # debug=0x8(10) rd=md0(7) ufs_shared_pa=0x+16hex+sp(33) hakios_kver=+47+sp(60)
composed = HEAD_MEASURED + len(s19)
assert composed < 607, "composed cmdline %d is not under the 607 cap" % composed
print("v19 payload cmdline: %d characters" % len(s19))
print("composed on machine: %d of 607 (head %d, measured from logdump-v18.bin @83231)" % (composed, HEAD_MEASURED))

# --- content guards ---
assert s19.count("loader_return_after=300") == 1
assert "en0_addr" not in s19, "en0_addr must be gone (budget)"
for arg in ("rec_secs=280", "rec_ring=1", "rec_mb=256", "ufs=2", "ufs_write=1",
            "var_hfs=ufs_darwin_data", "root_apfs=ufs_darwin", "hw_target=D22ap",
            "touchscreen=1", "buttons=1", "cpus=8", "bootcpu=7", "serial=0"):
    assert arg in s19, "%s lost" % arg
assert s19.count("rec_secs") == 1 and s19.count("rec_mb") == 1 and s19.count("rec_ring") == 1
assert "small_cores_after=0" in s19

data = s19.encode("ascii") + b"\0"
open(out, "wb").write(data)
print("sha256:", hashlib.sha256(data).hexdigest())
print("wrote", out, len(data), "bytes")
