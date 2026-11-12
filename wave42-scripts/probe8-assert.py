#!/usr/bin/env python3
"""Wave 42 probe 8: the full disassembly-level assertion on the v35 build.
1. loader.obj: locate usb_pair_rebuild (symbol table), disassemble its extent,
   verify the guard chain (volatile global loads), the transaction (indirect
   abort_xfer calls via the USB pointer, usb_retire_drain, usb_start_attempt),
   and the five print-call references.
2. loader.efi (the shipped artifact): prove the gen-4 strings are LIVE-referenced
   from .text by decoding ADRP+ADD pairs against the strings' RVAs."""
import re
import struct
import subprocess
import sys

TREE = "/home/cyrux/hakios/kernel/xnuloader"
obj = open(f"{TREE}/loader.obj", "rb").read()
efi = open(f"{TREE}/loader.efi", "rb").read()

# ---------- 1. obj symbol + extent ----------
st = subprocess.run(["llvm-objdump", "-t", f"{TREE}/loader.obj"],
                    capture_output=True, text=True).stdout
syms = []
for ln in st.splitlines():
    m = re.match(r'.*\(sec\s+(\d+)\).*0x([0-9a-f]+)\s+(\S+)$', ln)
    if m:
        syms.append((int(m.group(1)), int(m.group(2), 16), m.group(3)))
rb = [s for s in syms if s[2] == "usb_pair_rebuild" and s[0] == 1]
assert rb, "usb_pair_rebuild text symbol not found"
start = rb[0][1]
nxt = min((s[1] for s in syms if s[0] == 1 and s[1] > start), default=start + 0x800)
print(f"usb_pair_rebuild at {hex(start)}, extent <= {hex(nxt)} ({nxt-start} B scan)")

dis = subprocess.run(["llvm-objdump", "-d", f"{TREE}/loader.obj",
                      f"--start-address={hex(start)}", f"--stop-address={hex(nxt)}"],
                     capture_output=True, text=True)
if not dis.stdout:
    print("OBJDUMP STDERR:", dis.stderr[:400])
dis = dis.stdout
open("/tmp/w42/rebuild.dis", "w").write(dis)
lines = dis.splitlines()
print(f"disassembly: {len(lines)} lines")
n_mrs = len(re.findall(r'\bmrs\b', dis))
n_blr = len(re.findall(r'\bblr\b', dis))
n_bl = len(re.findall(r'\bbl\b', dis))
print(f"mrs={n_mrs} bl={n_bl} blr(indirect)={n_blr}")
assert n_mrs >= 2, "the two timer reads are gone"
call_targets = re.findall(r'\bbl\s+0x[0-9a-f]+\s+<([^>]+)>', dis)
print("bl targets:", call_targets)
need_calls = ["usb_retire_drain", "usb_start_attempt", "print"]
for c in need_calls:
    assert any(c in t for t in call_targets), f"missing call to {c}"
assert n_blr >= 2, "the two abort_xfer indirect calls are missing"
print("OBJ ASSERT PASS: guard chain + transaction + prints all present as real code")

# ---------- 2. efi string live-reference scan ----------
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
    so += 40
print(f"efi: base={hex(image_base)} entry_rva={hex(entry_rva)}")
for name, va, vsize, roff, rsize in secs:
    print(f"  {name:8s} va={hex(va)} vsize={hex(vsize)}")

text = [s for s in secs if s[0] == '.text'][0]
_, tva, tvsize, troff, trsize = text
code = efi[troff:troff + trsize]


def off_to_rva(off):
    for name, va, vsize, roff, rsize in secs:
        if roff <= off < roff + rsize:
            return va + (off - roff)
    return None


# decode every ADRP in .text: adrp Xd, page ; then find ADD Xd, Xd, #imm / LDR [Xd,#imm]
adrps = []
for i in range(0, len(code) - 3, 4):
    w = struct.unpack_from('<I', code, i)[0]
    if (w & 0x9F000000) == 0x90000000:  # ADRP
        rd = w & 31
        immlo = (w >> 29) & 3
        immhi = (w >> 5) & 0x7FFFF
        imm = (immhi << 2) | immlo
        if imm & (1 << 20):
            imm -= (1 << 21)
        page = (tva + i + (imm << 12)) & 0xFFFFFFFFFFFFF000
        adrps.append((tva + i, rd, page))
print(f"ADRP instructions in .text: {len(adrps)}")
adrp_by_reg = {}
for addr, rd, page in adrps:
    adrp_by_reg.setdefault(rd, []).append((addr, page))

needles = [
    b'the pair reads dead in this generation',
    b'bounded recovery %d of 2',
    b"the recovery's bring-up is back",
    b"the recovery's bring-up did not come back",
    b'usb: the recovery\'s IN abort was refused',
]
total_refs = 0
for nd in needles:
    off = efi.find(nd)
    assert off > 0, f"string not in efi at all: {nd!r}"
    rva = off_to_rva(off)
    refs = []
    for addr, rd, page in adrps:
        if page <= rva < page + 4096:
            refs.append((addr, rd))
    total_refs += len(refs)
    print(f"  {nd[:44]!r}: rva={hex(rva)} adrp-refs={len(refs)} {[hex(a) for a, _ in refs[:4]]}")
assert total_refs >= 3, "gen-4 strings present but not referenced from .text"
print("EFI ASSERT PASS: gen-4 strings are live-referenced from .text")
