#!/usr/bin/env python3
"""Wave 42 probe 10: EFI-level live-reference assertion on the shipped loader.efi.
Proves the gen-4 strings are referenced from .text by decoding ADRP+ADD/LDR pairs
against the strings' RVAs (the shipped image has no symbol table)."""
import struct

TREE = "/home/cyrux/hakios/kernel/xnuloader"
efi = open(f"{TREE}/loader.efi", "rb").read()
print("efi bytes:", len(efi))

e_lfanew = struct.unpack_from('<I', efi, 0x3C)[0]
coff = e_lfanew + 4
nsec = struct.unpack_from('<H', efi, coff + 2)[0]
opt_size = struct.unpack_from('<H', efi, coff + 16)[0]
opt = coff + 20
image_base = struct.unpack_from('<Q', efi, opt + 24)[0]
entry_rva = struct.unpack_from('<I', efi, opt + 16)[0]
secs = []
so = opt + opt_size
for i in range(nsec):
    name = efi[so:so + 8].rstrip(b'\0').decode('ascii', 'replace')
    vsize, va, rsize, roff = struct.unpack_from('<IIII', efi, so + 8)
    secs.append((name, va, vsize, roff, rsize))
    print(f"  {name:8s} va={hex(va)} vsize={hex(vsize)} roff={hex(roff)}")
    so += 40
print(f"entry_rva={hex(entry_rva)} (mkpayload's anchor expects 0x2140 on the reviewed build)")


def off_to_rva(off):
    for name, va, vsize, roff, rsize in secs:
        if roff <= off < roff + rsize:
            return va + (off - roff)
    return None


text = [s for s in secs if s[0] == '.text'][0]
_, tva, tvsize, troff, trsize = text
code = efi[troff:troff + trsize]

# decode ADRP pairs: track reg -> page; then ADD imm / LDR [reg,#imm] within window
# (conservative: each ADRP owns the following 16 instructions before its reg is re-set)
adrp_events = []
for i in range(0, len(code) - 3, 4):
    w = struct.unpack_from('<I', code, i)[0]
    if (w & 0x9F000000) == 0x90000000:
        rd = w & 31
        immlo = (w >> 29) & 3
        immhi = (w >> 5) & 0x7FFFF
        imm = (immhi << 2) | immlo
        if imm & (1 << 20):
            imm -= (1 << 21)
        page = (tva + i + (imm << 12)) & 0xFFFFFFFFFFFFF000
        adrp_events.append((tva + i, rd, page))

needles = [
    b'the pair reads dead in this generation',
    b'bounded recovery %d of 2',
    b"the recovery's bring-up is back",
    b"the recovery's bring-up did not come back",
    b'the IN gate is up',
    b'the service window is over',
]
# collect EVERY address .text materializes via ADRP+ADD (reg-flow conservative)
formed = []
for a, rd, page in adrp_events:
    idx = a - tva
    for j in range(idx + 4, min(idx + 64, len(code) - 3), 4):
        w = struct.unpack_from('<I', code, j)[0]
        if (w & 0x9F000000) == 0x90000000 and (w & 31) == rd:
            break  # the reg got re-assigned by another ADRP
        rn = (w >> 5) & 31
        if (w & 0xFF800000) == 0x91000000 and rn == rd:  # add Xd, Rd, #imm12
            imm12 = (w >> 10) & 0xFFF
            formed.append((page + imm12, hex(a)))
            break
print(f"addresses formed by ADRP+ADD pairs in .text: {len(formed)}")

total = 0
for nd in needles:
    off = efi.find(nd)
    if off < 0:
        print(f"  MISSING: {nd[:44]!r}")
        continue
    # walk back to the start of the containing string literal (previous NUL)
    lit = off
    while lit > 0 and efi[lit - 1] != 0:
        lit -= 1
    lit_rva = off_to_rva(lit)
    hits = [at for rva, at in formed if rva == lit_rva]
    total += len(hits)
    print(f"  {nd[:44]!r}: literal rva={hex(lit_rva)} exact refs={hits}")
    assert hits, f"literal not exactly referenced: {nd!r}"
assert total >= 4
print("EFI ASSERT PASS: exact ADRP+ADD pairs bind the gen-4 string literals from live .text code")
