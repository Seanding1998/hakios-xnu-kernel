#!/usr/bin/env python3
"""Wave 42 probe 12: hexdump the exact ADRP/ADD sites in the shipped efi."""
import struct

efi = open('/home/cyrux/hakios/kernel/xnuloader/loader.efi', 'rb').read()

def rva_off(rva):
    return rva - 0x1000 + 0x400  # .text va=0x1000 roff=0x400

for rva in range(0xeb20, 0xeb50, 4):
    off = rva_off(rva)
    w = struct.unpack_from('<I', efi, off)[0]
    note = ''
    if (w & 0x9F000000) == 0x90000000:
        rd = w & 31
        immlo = (w >> 29) & 3
        immhi = (w >> 5) & 0x7FFFF
        imm = (immhi << 2) | immlo
        if imm & (1 << 20):
            imm -= (1 << 21)
        page = (rva + (imm << 12)) & 0xFFFFFFFFFFFFF000
        note = f'ADRP x{rd} -> page {hex(page)}'
    elif (w & 0xFF800000) == 0x91000000:
        rd = w & 31
        rn = (w >> 5) & 31
        imm12 = (w >> 10) & 0xFFF
        note = f'ADD x{rd}, x{rn}, #{hex(imm12)}'
    elif (w & 0x7FFFFFFF) == 0x6C000000 >> 8:
        note = '??'
    print(f'{hex(rva)}: {w:08x}  {note}')
