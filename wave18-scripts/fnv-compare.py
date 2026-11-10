#!/usr/bin/env python3
"""Wave 18: compute host-side FNV-1a (the loader/kernel formula: h = 0xcbf29ce484222325,
h = (h ^ byte) * 0x100000001b3) over the first BYTES of each pulled partition
image, and (when given) diff against the kernel-side `ufs: check NAME: fnv HHH
over BYTES, ... ms` lines of the b23 kernel log.

usage: fnv-compare.py INTEL_DIR [B23_KERNEL_LOG]
"""
import sys, os, re

INTEL = sys.argv[1]
LOG = sys.argv[2] if len(sys.argv) > 2 else None

# the kernel's table (drivers/storage/hakios.ufs.c ufs_references[])
REFS = {
    "bluetooth": 503808, "abl": 208896, "aop": 208896, "xbl": 3706880,
    "tz": 3710976, "hyp": 3653632, "dsp": 67108864, "modem": 214265856,
}

def fnv1a(data):
    h = 0xcbf29ce484222325
    for b in data:
        h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    return h

host = {}
for name, nbytes in REFS.items():
    for slot in ("a", "b"):
        p = os.path.join(INTEL, "fnv-baseline", f"{name}_{slot}.bin")
        if os.path.isfile(p):
            data = open(p, "rb").read(nbytes)
            h = fnv1a(data)
            host[f"{name}_{slot}"] = (h, len(data))

print("host-side FNV-1a (64-bit):")
for name in REFS:
    if name in host:
        for slot, (h, n) in sorted(host[name].items()):
            print(f"  {name}_{slot}: fnv {h:016x} over {n} bytes")
    else:
        print(f"  {name}: NO BASELINE PULLED")

if LOG:
    print("\nkernel-side (b23 log) vs host:")
    txt = open(LOG, encoding="utf-8", errors="replace").read()
    kern = {}
    for m in re.finditer(r"ufs: check (\w+): fnv ([0-9a-f]+) over (\d+) bytes", txt):
        kern[m.group(1)] = (int(m.group(2), 16), int(m.group(3)))
    any_cmp = False
    for name, (kh, kn) in kern.items():
        cand = host.get(name, {})
        verdicts = []
        for slot, (hh, hn) in sorted(cand.items()):
            if hn != kn:
                verdicts.append(f"{slot}:bytecount-mismatch({hn}!={kn})")
            elif hh == kh:
                verdicts.append(f"{slot}:MATCH")
            else:
                verdicts.append(f"{slot}:MISMATCH")
        any_cmp = True
        print(f"  {name}: kernel fnv {kh:016x} over {kn} -> {'; '.join(verdicts) or 'no baseline'}")
    if not kern:
        print("  (no ufs: check lines found in the log)")
    if not any_cmp:
        print("  R1 comparison not possible this round")
