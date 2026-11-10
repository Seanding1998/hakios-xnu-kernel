#!/usr/bin/env python3
# Wave8: parse PE entry points and diff patched vs unpatched UsbConfigDxe
import struct, sys

def pe_info(path):
    d = open(path, "rb").read()
    # DOS header e_lfanew at 0x3c
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    assert d[pe:pe+4] == b"PE\0\0", path
    coff = pe + 4
    machine, nsec, _, _, _, optsize, chars = struct.unpack_from("<HHIIIHH", d, coff)
    opt = coff + 20
    magic = struct.unpack_from("<H", d, opt)[0]
    assert magic == 0x20B, (path, hex(magic))  # PE32+
    ep = struct.unpack_from("<I", d, opt + 16)[0]
    imagebase = struct.unpack_from("<Q", d, opt + 24)[0]
    return d, ep, imagebase, nsec, coff, opt

for p in sys.argv[1:]:
    d, ep, base, nsec, coff, opt = pe_info(p)
    print(f"{p}: entry RVA 0x{ep:x} imagebase 0x{base:x}")

if len(sys.argv) >= 3:
    a = open(sys.argv[1], "rb").read()
    b = open(sys.argv[2], "rb").read()
    print(f"\nlen patched={len(a)} unpatched={len(b)}")
    diffs = [i for i in range(min(len(a), len(b))) if a[i] != b[i]]
    print(f"differing bytes: {len(diffs)}")
    # group contiguous ranges
    ranges = []
    for i in diffs:
        if ranges and i <= ranges[-1][1] + 16:
            ranges[-1][1] = i
        else:
            ranges.append([i, i])
    for r in ranges:
        print(f"  range 0x{r[0]:x}..0x{r[1]:x} ({r[1]-r[0]+1} B)")
