#!/usr/bin/env python3
"""Wave 42: find the PAYLOAD_BASE movz/movk pair in the v35 loader.efi (the verify
pin assumed w8/w3 -- register allocation may have shifted with the v42 code changes)."""
import struct

ldr = open('/home/cyrux/hakios/kernel/xnuloader/loader.efi', 'rb').read()

def movz_f400(w):
    # movz Wd, #0xF400, lsl #16: sf=0 opc=10 100101 hw=01 imm16=0xF400 Rd=?
    return (w & 0xFFE00000) == 0x52A00000 and ((w >> 5) & 0xFFFF) == 0xF400 and ((w >> 21) & 3) == 1

hits = []
for m in range(0, len(ldr) - 40, 4):
    w = struct.unpack_from('<I', ldr, m)[0]
    if movz_f400(w):
        rd = w & 31
        nearby = []
        for k in range(1, 9):
            w2 = struct.unpack_from('<I', ldr, m + 4 * k)[0]
            # movk Wd, #imm16, lsl #16: sf=0 opc=11 100101 hw=01
            if (w2 & 0xFFE00000) == 0x72A00000 and (w2 & 31) == rd:
                imm16 = (w2 >> 5) & 0xFFFF
                nearby.append((k, hex(w2), hex(imm16)))
        hits.append((hex(m), rd, nearby))

print(f"loader.efi bytes: {len(ldr)}")
for h in hits:
    print(f"  movz@{h[0]} Rd=w{h[1]} movk-same-reg: {h[2]}")

# the XNUP magic constant 0x50554E58 = movz #0x4E58 + movk #0x5055 lsl16 (32-bit build via w-regs)
for m in range(0, len(ldr) - 40, 4):
    w = struct.unpack_from('<I', ldr, m)[0]
    if (w & 0xFFE00000) == 0x52A00000 and ((w >> 5) & 0xFFFF) == 0x4E58:
        rd = w & 31
        for k in range(1, 5):
            w2 = struct.unpack_from('<I', ldr, m + 4 * k)[0]
            if (w2 & 0xFFE00000) == 0x72A00000 and (w2 & 31) == rd and ((w2 >> 5) & 0xFFFF) == 0x5055:
                print(f"  XNUP-magic pair: movz@{hex(m)} w{rd} + movk@+{k} (#0x5055)")
