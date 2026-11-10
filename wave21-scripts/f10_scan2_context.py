#!/usr/bin/env python3
"""F10 scan pass 2: distinguish data-literal 0xF0000000 from ADRP-instruction noise.

- AArch64 ADRP encoding 0xF0000000 (= adrp x0, pc+0x3000) is a common instruction;
  raw '00 00 00 F0' hits are therefore ambiguous.
- This pass reports:
  * aligned 4-byte word hits with +/-8 byte hex context (literal pools are 8-aligned)
  * 8-byte qword pointer hits with context
  * per-file counts split into ADRP-shaped (unaligned/odd) vs others
Read-only.
"""
import sys, os, json

HOME = os.path.expanduser("~")
CAND = [
    os.path.join(HOME, "hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd"),
]
BUILD = os.path.join(HOME, "hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/AARCH64")
for root, _d, files in os.walk(BUILD):
    for f in files:
        if f.lower().endswith(".efi") and "/DEBUG/" not in root.replace(os.sep, "/") and "/OUTPUT/" not in root.replace(os.sep, "/"):
            CAND.append(os.path.join(root, f))
BIN = os.path.join(HOME, "hakios/uefi-udon/Binaries")
if os.path.isdir(BIN):
    for root, _d, files in os.walk(BIN):
        for f in files:
            CAND.append(os.path.join(root, f))
for p in sys.argv[1:]:
    CAND.append(os.path.abspath(p))

WORD = b"\x00\x00\x00\xf0"
QWORD = b"\x00\x00\x00\xf0\x00\x00\x00\x00"

report = []
for path in sorted(set(CAND)):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        continue
    if len(data) == 0:
        continue
    hits, start = [], 0
    while True:
        i = data.find(WORD, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    if not hits:
        continue
    adrp_shaped = 0
    aligned_hits = []
    for i in hits:
        # ADRP x0: word value 0xF0000000 exactly, anywhere -> instruction candidate
        if i % 4 == 0 and data[i:i+4] == WORD:
            aligned_hits.append(i)
        if i % 4 == 3:
            adrp_shaped += 1  # instruction stream (4-aligned instrs have bytes at i%4==0; i%4==3 means shifted)
    ctx = []
    for i in aligned_hits[:6] + [h for h in hits if h % 4 != 0][:2]:
        lo = max(0, i - 8)
        ctx.append({"off": i, "aligned": i % 8 == 0,
                    "hex": data[lo:i+12].hex(" ")})
    report.append({"file": path, "size": len(data), "total": len(hits),
                   "aligned4": len(aligned_hits), "adrp_shaped_misaligned": adrp_shaped,
                   "context": ctx})

print(f"files scanned: {len(set(CAND))}, files with hits: {len(report)}")
print(f"{'file':<64} {'tot':>5} {'al4':>5} {'shft':>5}")
for r in report:
    rel = r["file"].replace(HOME, "~")
    print(f"{rel:<64} {r['total']:>5} {r['aligned4']:>5} {r['adrp_shaped_misaligned']:>5}")

print("\n=== context samples (files with >=1 aligned-8 hit) ===")
for r in report:
    for c in r["context"]:
        if c["aligned"]:
            print(f"{r['file'].replace(HOME,'~')} @0x{c['off']:x}: {c['hex']}")
            break

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "f10_scan2_result.json")
with open(out, "w") as fh:
    json.dump(report, fh, indent=1)
print(f"\njson -> {out}")
