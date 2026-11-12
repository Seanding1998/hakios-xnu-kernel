#!/usr/bin/env python3
"""Wave 38 fix generation 4, hardening: LLVM 22.1.8 at -O1 eliminated
usb_pair_rebuild entirely (IPSCCP folded the whole body to an early return -- the
emitted binary was three instructions: mrs; mrs; ret -- and __attribute__((used))
only forced the stub's emission, not the body). The USB lifecycle paths are
correctness-critical and were validated by the isolation suite at -O0 semantics;
they are now pinned to that semantics in the shipped build with optnone+noinline.

Functions pinned: usb_wall_gate, usb_gate_reset, usb_pump, usb_arm_rx,
usb_retire_drain, usb_wait, usb_rx, usb_tx, usb_poll_command, usb_pair_rebuild,
usb_stale_wipe. The hot bulk-data paths (download/upload chunk loops) are NOT in
these functions (usb_tx/usb_rx only submit and wait); the pump's 20 ms cadence
dominates its cost.

usage: patch-loader-v38g-optnone.py LOADER_C
"""
import re
import sys

path = sys.argv[1]
src = open(path, encoding="utf-8").read()
orig = src
lines = src.split("\n")

PINNED = ["usb_wall_gate", "usb_gate_reset", "usb_pump", "usb_arm_rx", "usb_retire_drain",
          "usb_wait", "usb_rx", "usb_tx", "usb_poll_command", "usb_pair_rebuild", "usb_stale_wipe"]

patched = 0
for fn in PINNED:
    for i, ln in enumerate(lines):
        if ln == fn + "(void)" or (ln.startswith(fn + "(") and ln.endswith(")")):
            if i > 0 and lines[i - 1].startswith("static"):
                lines[i - 1] = "__attribute__((optnone, noinline)) " + lines[i - 1]
                patched += 1
                break
            if i > 0 and lines[i - 1].startswith("__attribute__"):
                break   # already pinned
    else:
        raise SystemExit(f"definition layout not found for: {fn}")

src = "\n".join(lines)
assert src != orig
open(path, "w", encoding="utf-8", newline="").write(src)
print(f"optnone+noinline pinned on {patched} functions")
