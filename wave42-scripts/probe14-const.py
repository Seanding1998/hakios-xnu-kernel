#!/usr/bin/env python3
"""Wave 42 probe 14: how are PAYLOAD_BASE=0xF4000000 and the XNUP magic 0x50554E58
formed in the v35 loader.efi? Decode all movz/movk pairs per register and report
the formed constants, so the verify pin can be semantic (constant formation),
not layout-fragile."""
import struct

ldr = open('/home/cyrux/hakios/kernel/xnuloader/loader.efi', 'rb').read()
n = len(ldr) // 4

def decode(i):
    w = struct.unpack_from('<I', ldr, i * 4)[0]
    if (w & 0xFFE00000) == 0x52A00000:  # movz w, #imm, lsl #16 (sf=0 opc=10 hw=01)
        return ('movz16', w & 31, (w >> 5) & 0xFFFF)
    if (w & 0xFFE00000) == 0x52800000:  # movz w, #imm (hw=00)
        return ('movz0', w & 31, (w >> 5) & 0xFFFF)
    if (w & 0xFFE00000) == 0x72A00000:  # movk w, #imm, lsl #16
        return ('movk16', w & 31, (w >> 5) & 0xFFFF)
    if (w & 0xFFE00000) == 0x72800000:  # movk w, #imm (hw=00)
        return ('movk0', w & 31, (w >> 5) & 0xFFFF)
    return None

# walk per-register chains: within a 12-event window without re-assignment
events = [(i, decode(i)) for i in range(n) if decode(i)]
print(f"movz/movk events: {len(events)}")
formed = {}
for idx, (i, (op, rd, imm)) in enumerate(events):
    val = None
    for j in range(idx, min(idx + 12, len(events))):
        op2, rd2, imm2 = events[j][1]
        if rd2 != rd:
            continue
        if op2 == 'movz16':
            val = imm2 << 16
        elif op2 == 'movz0':
            val = imm2
        elif op2 == 'movk16' and val is not None:
            val = (val & 0x0000FFFF) | (imm2 << 16)
        elif op2 == 'movk0' and val is not None:
            val = (val & 0xFFFF0000) | imm2
        if val in (0xF4000000, 0x50554E58):
            formed.setdefault(val, []).append((hex(i * 4), hex(events[j][0] * 4), hex(val)))
            break
for val, sites in formed.items():
    print(f"  constant {hex(val)}: formed at {sites[:6]} (total {len(sites)})")
if not formed:
    print("  NEITHER constant formed via movz/movk pairs -- check literal pools / mov-movk pairs")
