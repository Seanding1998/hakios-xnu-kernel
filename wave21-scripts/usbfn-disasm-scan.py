#!/usr/bin/env python3
"""Scan vendor UsbFnDwc3Dxe (and UsbConfigDxe) for DWC3 base/offset register usage."""
import struct, os, glob

root = os.path.expanduser("~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/Ffs")
MODULES = {"94F8A6A7": "UsbfnDwc3Dxe", "CD823A4D": "UsbConfigDxe", "3299A266": "UsbDeviceDxe",
           "0A134F0E": "UsbInitDxe", "11FAED4C": "UsbPwrCtrlDxe"}

def find_pe(d):
    # vendor FFS PEs: MZ at some offset with e_lfanew relative
    i = d.find(b"MZ", 0x18)
    while i >= 0:
        off = struct.unpack_from("<I", d, i + 0x3C)[0]
        pe = i + off
        if off <= 0x1000 and pe + 266 <= len(d) and d[pe:pe + 4] == b"PE\0\0":
            return i, pe
        i = d.find(b"MZ", i + 1)
    return None, None

for p in sorted(glob.glob(root + "/*/*.ffs")):
    name = os.path.basename(os.path.dirname(p))
    key = name.split("-")[0]
    if key not in MODULES:
        continue
    d = open(p, "rb").read()
    mz, pe = find_pe(d)
    if pe is None:
        print(MODULES[key], ": no PE"); continue
    nsec = struct.unpack_from("<H", d, pe + 6)[0]
    optsz = struct.unpack_from("<H", d, pe + 20)[0]
    sect = pe + 24 + optsz
    text = None
    for i in range(nsec):
        s = d[sect + 40*i: sect + 40*i + 40]
        nm = s[:8].rstrip(b"\x00").decode()
        vsz, va, rsz, praw = struct.unpack_from("<IIII", s[8:24])
        if nm == ".text":
            text = (va, vsz, praw, rsz)
    print("%-14s pe@%x .text=%s" % (MODULES[key], pe, text))

    # scan the whole module bytes for the interesting 32-bit offsets as literal words
    for off, label in ((0xC110, "GCTL"), (0xC2C0, "GUSB3PIPECTL"), (0xC200, "GUSB2PHYCFG"),
                       (0xC704, "DCTL"), (0xC70C, "DSTS"), (0xC718, "DEVTEN")):
        needle = struct.pack("<I", off)
        cnt = 0
        j = d.find(needle)
        while j >= 0:
            cnt += 1
            j = d.find(needle, j + 1)
        print("    literal %-14s x%d" % (label, cnt))

    # scan for the 64-bit base literal 0x0A600000 (u64 LE)
    n64 = d.count(bytes.fromhex("0000000a00000000"))
    print("    u64 0x0A600000 x%d" % n64)
    # and 32-bit 0x0A600000's page-presence via adrp-friendly forms: count 0x0A6xxxxx words
    w = 0
    for j in range(0, len(d) - 4, 4):
        v = struct.unpack_from("<I", d, j)[0]
        if 0x0A600000 <= v < 0x0A700000:
            w += 1
    print("    u32 words in 0x0A6xxxxx x%d" % w)
