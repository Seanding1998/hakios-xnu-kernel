#!/usr/bin/env python3
# Wave8: locate GUIDs in driver images and give RVA<->file mapping
import struct, sys, uuid

GUIDS = {
    "gUsbControllerInitGuid": "1c0cffce-fc8d-4e44-8c78-9c9e5b530d36",
    "gEfiUsbDeviceProtocolGuid": "d9d9ce48-44b8-4f49-8e3e-2a3b927dc6c1",
    "gEfiUsbConfigProtocolGuid?": "b0760469-970c-487a-a4b5-28db7b45cef1",  # actually ChipInfo
    "gEfiSMEMProtocolGuid": "f4e5c7d0-d239-47cb-aacd-7f66ef763238",
    "gEfiPlatformInfoProtocolGuid": "157a5c45-21b2-43c5-ba7c-822fee5fe599",
    "EB97088E(unknown)": "eb97088e-cfdf-49c6-be4b-d906a5b20e86",
    "UsbInitDepex 50E722B0": "50e722b0-ceb2-428e-bd5b-d51812d03708",
}

def sections(d):
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    coff = pe + 4
    nsec = struct.unpack_from("<H", d, coff + 2)[0]
    optsize = struct.unpack_from("<H", d, coff + 16)[0]
    sec0 = coff + 20 + optsize
    out = []
    for i in range(nsec):
        o = sec0 + 40 * i
        name = d[o:o+8].rstrip(b"\0").decode()
        vsize, va, rsize, roff = struct.unpack_from("<IIII", d, o + 8)
        out.append((name, va, vsize, roff, rsize))
    return out

def find_guids(d):
    hits = []
    for name, g in GUIDS.items():
        b = uuid.UUID(g).bytes_le
        i = d.find(b)
        while i != -1:
            hits.append((name, i))
            i = d.find(b, i + 1)
    return hits

for p in sys.argv[1:]:
    d = open(p, "rb").read()
    print(f"### {p}")
    secs = sections(d)
    for name, va, vsize, roff, rsize in secs:
        print(f"  sec {name:8} RVA 0x{va:06x} vsize 0x{vsize:06x} file 0x{roff:06x} raw 0x{rsize:06x}")
    def rva(fo):
        for name, va, vsize, roff, rsize in secs:
            if roff <= fo < roff + rsize:
                return va + (fo - roff)
        return None
    for name, fo in find_guids(d):
        print(f"  GUID {name:28} file 0x{fo:06x} rva 0x{rva(fo)}")
    print()
