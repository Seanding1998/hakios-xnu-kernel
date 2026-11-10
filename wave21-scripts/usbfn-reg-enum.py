#!/usr/bin/env python3
"""Enumerate the exact 0x0A6xxxxx register addresses the vendor USB modules touch."""
import struct, os, glob

root = os.path.expanduser("~/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/Ffs")
MODULES = {"94F8A6A7": "UsbfnDwc3Dxe", "CD823A4D": "UsbConfigDxe", "3299A266": "UsbDeviceDxe",
           "0A134F0E": "UsbInitDxe"}

KNOWN = {0x0A6C110: "GCTL", 0x0A6C2C0: "GUSB3PIPECTL0", 0x0A6C200: "GUSB2PHYCFG0",
         0x0A6C704: "DCTL", 0x0A6C70C: "DSTS", 0x0A6C718: "DEVTEN", 0x0A6B000: "GEVNTADR0?",
         0x0A6C220: "GUSB2PHYCFG1"}

for p in sorted(glob.glob(root + "/*/*.ffs")):
    name = os.path.basename(os.path.dirname(p))
    key = name.split("-")[0]
    if key not in MODULES:
        continue
    d = open(p, "rb").read()
    words = {}
    for j in range(0, len(d) - 4):
        v = struct.unpack_from("<I", d, j)[0]
        if 0x0A600000 <= v < 0x0A700000 and (v & 3) == 0:
            words[v] = words.get(v, 0) + 1
    print(MODULES[key], "0x0A6xxxxx words:")
    for v in sorted(words):
        tag = KNOWN.get(v, "")
        print("    0x%08X x%d %s" % (v, words[v], tag))
