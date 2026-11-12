#!/usr/bin/env python3
"""Wave 42 probe 5: does loader.efi 9d2799a7 really contain usb_pair_rebuild's body?
Parse the PE, locate the gen-4 strings' RVAs, then scan the .text disassembly for
references (adrp+add pairs) to those RVAs, and report the code around them."""
import re
import struct
import subprocess
import sys

path = sys.argv[1]
data = open(path, 'rb').read()
print("file bytes:", len(data))

# --- PE section table ---
e_lfanew = struct.unpack_from('<I', data, 0x3C)[0]
assert data[e_lfanew:e_lfanew + 4] == b'PE\0\0'
coff = e_lfanew + 4
nsec = struct.unpack_from('<H', data, coff + 2)[0]
opt_size = struct.unpack_from('<H', data, coff + 16)[0]
opt = coff + 20
image_base = struct.unpack_from('<Q', data, opt + 24)[0]
entry_rva = struct.unpack_from('<I', data, opt + 16)[0]
print(f"image_base={image_base:#x} entry_rva={entry_rva:#x} sections={nsec}")
secs = []
so = opt + opt_size
for i in range(nsec):
    name = data[so:so + 8].rstrip(b'\0').decode()
    vsize, va, rsize, roff = struct.unpack_from('<IIII', data, so + 8)
    secs.append((name, va, vsize, roff, rsize))
    print(f"  {name:8s} va={va:#010x} vsize={vsize:#x} roff={roff:#x} rsize={rsize:#x}")
    so += 40

def off_to_rva(off):
    for name, va, vsize, roff, rsize in secs:
        if roff <= off < roff + rsize:
            return va + (off - roff)
    return None

# --- find the strings ---
needles = [
    b'the pair reads dead in this generation',
    b'bounded recovery %d of 2',
    b"the recovery's bring-up is back",
    b'the IN gate is up',
]
rvas = {}
for n in needles:
    off = data.find(n)
    rva = off_to_rva(off) if off >= 0 else None
    rvas[n] = rva
    print(f"string {n[:40]!r}: off={off:#x} rva={rva if rva is None else hex(rva)}")

# --- disassemble .text and find adrp/add or adr references to those pages ---
text = [s for s in secs if s[0] == '.text'][0]
name, va, vsize, roff, rsize = text
dis = subprocess.run(
    ['llvm-objdump', '-d', '--start-address', hex(va), '--stop-address', hex(va + min(vsize, rsize)), path],
    capture_output=True, text=True).stdout
open('/tmp/w42/efi.dis', 'w').write(dis)
print("disassembly lines:", dis.count('\n'))

# ADRP+ADD: track adrp destination register -> page address; add with pageoff -> full address
lines = dis.splitlines()
refs = {n: [] for n in needles}
adrp_reg = {}
adr_re = re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{8}\s+)?(adrp|x?adr)\s+(x\d+),\s*(?:#)?([0-9a-fx]+)')
add_re = re.compile(r'^\s*([0-9a-f]+):\s+(?:[0-9a-f]{8}\s+)?add\s+(x\d+),\s*(x\d+),\s*#?,?lsl #12|add\s+(x\d+),\s*(x\d+),\s*(?:#)?([0-9a-fx]+)')
# simpler: llvm-objdump prints e.g. "adrp x0, 0xa1001000" and "add x0, x0, #0x123" (pageoff annotated)
cur_adrp = {}
for ln in lines:
    m = re.search(r'\b(adrp)\s+(x\d+),\s*#?([0-9a-f]+)', ln)
    if m:
        cur_adrp[m.group(2)] = int(m.group(3), 16)
        continue
    m = re.search(r'\badd\s+(x\d+),\s*(x\d+),\s*#([0-9a-f]+)\b', ln)
    if m and m.group(2) in cur_adrp:
        full = cur_adrp[m.group(2)] + int(m.group(3), 16)
        for n, r in rvas.items():
            if r is not None and full <= r < full + 4096:
                refs[n].append((int(ln.split(':')[0], 16), hex(full)))
    m = re.search(r'\bldr\s+(x\d+|w\d+),\s*\[(x\d+),\s*#([0-9a-f]+)\]', ln)
    if m and m.group(2) in cur_adrp:
        full = cur_adrp[m.group(2)] + int(m.group(3), 16)
        for n, r in rvas.items():
            if r is not None and full <= r < full + 4096:
                refs[n].append((int(ln.split(':')[0], 16), hex(full)))

for n in needles:
    print(f"refs to {n[:40]!r}: {len(refs[n])}")
    for a, p in refs[n][:6]:
        print(f"   at {hex(a)} (page {p})")

# for the rebuild string: print 30 lines around its first reference
if refs[needles[0]]:
    at = refs[needles[0]][0][0]
    for i, ln in enumerate(lines):
        mm = re.match(r'^\s*([0-9a-f]+):', ln)
        if mm and abs(int(mm.group(1), 16) - at) <= 60:
            pass
    idx = next(i for i, ln in enumerate(lines)
               if re.match(r'^\s*([0-9a-f]+):', ln) and int(re.match(r'^\s*([0-9a-f]+):', ln).group(1), 16) >= at - 48)
    print("== context around the first reference to the rebuild string ==")
    print('\n'.join(lines[max(0, idx - 20):idx + 40]))
