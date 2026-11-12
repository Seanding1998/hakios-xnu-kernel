#!/usr/bin/env python3
"""Wave 42 probe 8b: COFF-relocation-level proof that usb_pair_rebuild's body is real
in the v35 loader.obj. Parses the COFF symbol + relocation tables directly, collects
the relocations that fall inside usb_pair_rebuild's extent, and resolves them to
symbol names. Asserts the recovery's full call set + its five print strings."""
import struct
import sys

TREE = "/home/cyrux/hakios/kernel/xnuloader"
data = open(f"{TREE}/loader.obj", "rb").read()

machine, nsec, _ts, sym_ptr, n_syms, opt_size, _chars = struct.unpack_from('<HHIIIHH', data, 0)
print(f"sections={nsec} symbols={n_syms}")

# section table (right after the 20-byte file header + optional header)
secs = []
so = 20 + opt_size
for i in range(nsec):
    name = data[so:so + 8].rstrip(b'\0').decode('ascii', 'replace')
    vsize, va, rsize, roff, rel_ptr, _ln, n_rel, _nln, _ch = struct.unpack_from('<IIIIIIHHI', data, so + 8)
    secs.append((name, va, rsize, roff, rel_ptr, n_rel))
    so += 40
for s in secs:
    print(f"  {s[0]:8s} va={hex(s[1])} size={hex(s[2])} relocs={s[5]}")

# symbols (18 bytes each; skip aux records)
syms = []
so = sym_ptr
for i in range(n_syms):
    name = data[so:so + 8]
    if name == b'\0\0\0\0\0\0\0\0':
        str_off = struct.unpack_from('<I', data, so + 4)[0]
        st_ptr = sym_ptr + 18 * n_syms
        nm = data[st_ptr + str_off:].split(b'\0', 1)[0].decode('ascii', 'replace')
    else:
        nm = name.rstrip(b'\0').decode('ascii', 'replace')
    value, secnum, _typ, _cls, naux = struct.unpack_from('<IhhBB', data, so + 8)
    syms.append((nm, value, secnum))
    so += 18 * (1 + naux)

byname = {}
for nm, value, secnum in syms:
    byname.setdefault(nm, []).append((value, secnum))

rb = [s for s in syms if s[0] == "usb_pair_rebuild"]
assert rb, "usb_pair_rebuild symbol missing"
# section number is 1-based; find its address within .text
text = [s for s in secs if s[0] == ".text"][0]
sec_idx = secs.index(text) + 1
fn = [s for s in rb if s[2] == sec_idx][0]
start = fn[1]
# extent = next .text symbol after start
ends = sorted(v for nm2, v, sn in syms if sn == sec_idx and v > start)
end = ends[0] if ends else start + 0x800
print(f"usb_pair_rebuild: {hex(start)}..{hex(end)} ({end-start} B)")

# relocations of .text inside the extent
nm2, va, rsize, roff, rel_ptr, n_rel = text
hits = []
for i in range(n_rel):
    va_r, sym_idx, typ = struct.unpack_from('<IIH', data, rel_ptr + i * 10)
    if start <= va_r < end:
        hits.append((va_r, typ, syms[sym_idx][0]))
print(f"relocations inside usb_pair_rebuild: {len(hits)}")
for va_r, typ, nm3 in sorted(hits):
    print(f"  {hex(va_r)}: {nm3[:60]}")

joined = " ".join(nm3 for _, _, nm3 in hits)
need = [
    ("the pair reads dead string", "MGBPICDP"),
    ("IN abort was refused string", "PEFDBFNM"),
    ("OUT abort was refused string", "FKMJAFGM"),
    ("bring-up did not come back string", "GDAEMIE"),
    ("bring-up is back string", "HLNHMHIM"),
    ("usb_retire_drain call", "usb_retire_drain"),
    ("usb_start_attempt call", "usb_start_attempt"),
    ("usb_wait_pumped call", "usb_wait_pumped"),
    ("usb_gate_reset call", "usb_gate_reset"),
    ("print calls", "print"),
]
ok = True
for label, token in need:
    c = joined.count(token)
    ok = ok and c >= 1
    print(f"  {'PASS' if c else 'FAIL'} {label}: {c} reloc(s)")
assert ok, "the recovery's body is not fully present"
print("COFF-RELOC ASSERT PASS: usb_pair_rebuild is a real, complete function in the v35 obj")
