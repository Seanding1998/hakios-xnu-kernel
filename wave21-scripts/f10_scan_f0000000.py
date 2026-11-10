#!/usr/bin/env python3
"""F10 read-only scan: find 0xF0000000 immediates in UEFI build outputs + FD.

Pattern classes (all little-endian byte views):
  WORD   : 4-byte literal 0xF0000000            -> 00 00 00 F0
  QWORD  : 8-byte pointer 0x00000000F0000000    -> 00 00 00 F0 00 00 00 00
  MOVK64 : movk xN, #0xF000, lsl #16 = 0xF29E0000|Rd -> (Rd) 00 9E F2
  MOVK32 : movk wN, #0xF000, lsl #16 = 0x729E0000|Rd -> (Rd) 00 9E 72
  MOVZ24 : movz xN, #0xF0, lsl #24   = 0xD2A01E00|Rd -> (Rd) 1E A0 D2

Usage: python3 f10_scan_f0000000.py [extra-path ...]
Default targets: Build/udonPkg/DEBUG_CLANGPDB/AARCH64/**/*.(efi|dll|bin)
                 Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd
Read-only: only opens files for reading.
"""
import sys, os, json

HOME = os.path.expanduser("~")
BUILD = os.path.join(HOME, "hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/AARCH64")
FD = os.path.join(HOME, "hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd")

targets = []
if os.path.isdir(BUILD):
    for root, _dirs, files in os.walk(BUILD):
        for f in files:
            if f.lower().endswith((".efi", ".dll", ".bin")):
                targets.append(os.path.join(root, f))
if os.path.exists(FD):
    targets.append(FD)
for p in sys.argv[1:]:
    if os.path.isdir(p):
        for root, _dirs, files in os.walk(p):
            for f in files:
                targets.append(os.path.join(root, f))
    elif os.path.exists(p):
        targets.append(os.path.abspath(p))

MOVK64 = [bytes([rd, 0x00, 0x9E, 0xF2]) for rd in range(32)]
MOVK32 = [bytes([rd, 0x00, 0x9E, 0x72]) for rd in range(32)]
MOVZ24 = [bytes([rd, 0x1E, 0xA0, 0xD2]) for rd in range(32)]
WORD = b"\x00\x00\x00\xf0"
QWORD = b"\x00\x00\x00\xf0\x00\x00\x00\x00"


def find_all(data, pat, limit=8):
    hits, start = [], 0
    while len(hits) < 200:
        i = data.find(pat, start)
        if i < 0:
            break
        hits.append(i)
        start = i + 1
    return hits


results = []
for path in sorted(set(targets)):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as e:
        print(f"SKIP {path}: {e}")
        continue
    word = find_all(data, WORD)
    qword = find_all(data, QWORD)
    movk64 = sum(len(find_all(data, p)) for p in MOVK64)
    movk32 = sum(len(find_all(data, p)) for p in MOVK32)
    movz24 = sum(len(find_all(data, p)) for p in MOVZ24)
    if word or qword or movk64 or movk32 or movz24:
        results.append({
            "file": path,
            "size": len(data),
            "word_0xF0000000": len(word),
            "word_offsets": word[:8],
            "qword_ptr": len(qword),
            "qword_offsets": qword[:8],
            "movk64": movk64,
            "movk32": movk32,
            "movz24": movz24,
        })

print(f"scanned {len(set(targets))} files, {len(results)} with hits\n")
hdr = f"{'file':<70} {'w':>4} {'q':>3} {'mk64':>4} {'mk32':>4} {'mz24':>4}"
print(hdr)
print("-" * len(hdr))
for r in results:
    rel = r["file"]
    print(f"{rel:<70} {r['word_0xF0000000']:>4} {r['qword_ptr']:>3} "
          f"{r['movk64']:>4} {r['movk32']:>4} {r['movz24']:>4}")

print("\n=== word-literal (00 00 00 F0) offsets per file ===")
for r in results:
    if r["word_0xF0000000"]:
        offs = ",".join(hex(o) for o in r["word_offsets"])
        print(f"{r['file']}: n={r['word_0xF0000000']} first={offs}")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "f10_scan_result.json")
with open(out, "w") as fh:
    json.dump(results, fh, indent=1)
print(f"\nfull json -> {out}")
