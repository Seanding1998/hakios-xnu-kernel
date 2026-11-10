#!/usr/bin/env python3
"""Wave 23 Round 2 verification of udon-hakios-grafted-v19b.img.

Shape identical to verify-udon-hakios-v19.py, with the loader swapped for the v19b build
(9dc2f5db: the coordinator's four items -- softened re-throw, service phase early, the raw
UsbFn code, settle 5 s) and every other entry pinned to the v19 payload's bytes.

usage: verify-udon-hakios-v19b.py IMG STOCK SHIM FD PAYLOAD_V19B PAYLOAD_V19 CMDLINE_V19 KERNEL_FILE
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD_V19B, PAYLOAD_V19, CMDLINE_V19, KFILE = sys.argv[1:9]

def sha(b): return hashlib.sha256(b).hexdigest()
ok = 0

def check(name, cond, detail=""):
    global ok
    if not cond:
        sys.exit(f"FAIL: {name} {detail}")
    ok += 1
    print(f"  PASS {name} {detail}")

img = open(IMG, "rb").read()
stock = open(STOCK, "rb").read()
shim = open(SHIM, "rb").read()
fd = open(FD, "rb").read()
payload = open(PAYLOAD_V19B, "rb").read()
payload_v19 = open(PAYLOAD_V19, "rb").read()
cmdline_v19 = open(CMDLINE_V19, "rb").read()
kfile = open(KFILE, "rb").read()

print("[header]")
check("ANDROID! magic", img[:8] == b"ANDROID!")
diff = [i for i in range(4096) if img[i] != stock[i]]
check("header diff vs stock is kernel_size/ramdisk_size only",
      all(8 <= i < 16 for i in diff), f"diff bytes {diff}")
ksz = struct.unpack_from("<I", img, 8)[0]
print(f"  kernel_size={ksz}")

print("[payload pages]")
pages = (ksz + 4095) // 4096
content_end = 4096 + pages * 4096
kernel = img[4096:4096 + ksz]
check("kernel zero-padded to page", img[4096 + ksz:content_end] == b"\0" * (content_end - 4096 - ksz))

print("[gzip round-trip]")
g = gzip.decompress(kernel)
expected = shim + fd + payload
expected += b"\0" * (-len(expected) % 16)
check("gunzip == shim+fd+payload(+pad)", g == expected, f"{len(g)} B")
check("sha256 decompressed", sha(g))

print("[shim header]")
text_off, image_size = struct.unpack_from("<QQ", g, 8)
check("text_offset == 0xA7100000", text_off == 0xA7100000, hex(text_off))
check("image_size == shim+fd", image_size == len(shim) + len(fd), hex(image_size))
check("ARMd magic @0x38", g[0x38:0x3C] == b"ARMd")

print("[FD]")
check("_FVH at shim+0x28", g[len(shim) + 0x28: len(shim) + 0x2C] == b"_FVH")
check("FD bytes equal source", g[len(shim):len(shim) + len(fd)] == fd)
check("FD is the untouched v4+ build (8924cb67)", sha(fd).startswith("8924cb67"), sha(fd)[:16])
check("shim is the untouched build (108ce972)", sha(shim).startswith("108ce972"), sha(shim)[:16])

print("[XNUP payload]")
poff = len(shim) + len(fd)
magic, size = struct.unpack_from("<II", g, poff)
check("magic XNUP", magic == 0x50554E58, f"{magic:08x}")
check("Size == len-8", size == len(payload) - 8, f"{size}")
check("container byte-equal to source", g[poff:poff + len(payload)] == payload)
check("payload fits the 64 MB window", len(payload) <= 0x4000000 - 0x1000, f"{len(payload)} B")

def walk_entries(buf, base, size):
    out = {}
    off = base + 8
    while off + 24 <= base + 8 + size:
        name = buf[off:off + 16].split(b"\0")[0].decode()
        if not name:
            break
        esz, _ = struct.unpack_from("<II", buf, off + 16)
        out[name] = (off + 24, esz)
        off += 24 + (esz + 15) // 16 * 16
    return out

entries = walk_entries(g, poff, size)
check("entries (usb joins: the USB server is up before the kernel)",
      set(entries) == {"loader.efi", "kernel", "resident", "ramdisk", "cmdline", "kernel.ver", "usb"},
      str({k: v[1] for k, v in entries.items()}))
cmd_off, cmd_sz = entries["cmdline"]
cmd = g[cmd_off:cmd_off + cmd_sz].decode().rstrip("\0")
print(f"  cmdline: {cmd}")
print("[cmdline]")
check("cmdline = the v19 bytes exactly (Round 2 moves no boot-arg)",
      g[cmd_off:cmd_off + cmd_sz] == cmdline_v19)
check("cmdline ends with rec_mb=256", cmd.endswith("rec_secs=280 rec_ring=1 rec_mb=256"))
check("loader_return_after=300 present, en0_addr absent, budget 488+110=598<607",
      cmd.count("loader_return_after=300") == 1 and "en0_addr" not in cmd and len(cmd) == 488)

def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e19b = payload_entries(payload)
e19 = payload_entries(payload_v19)
print("[entries]")
check("kernel == the v15/v16 build carried by v19, byte for byte",
      e19b["kernel"] == kfile == e19["kernel"], f"sha256 {sha(e19b['kernel'])[:16]}")
check("kernel carries the Mini display + surface drivers (the stack under test)",
      all(s in e19b["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",
                                        b"IOCoreSurfaceRoot", b"created surface %u: %ux%u",
                                        b"recording %u s of the screen")))
check("kernel carries the recording boot-arg tunables",
      all(s in e19b["kernel"] for s in (b"rec_secs", b"rec_mb", b"rec_ring", b"rec_step")))
check("kernel.ver byte-equal to the v19 entry (afd473f5 stamp)",
      e19b["kernel.ver"] == e19["kernel.ver"] and sha(e19b["kernel.ver"]).startswith("afd473f5"))
check("resident entry byte-equal to the v19 entry", e19b["resident"] == e19["resident"], f"{len(e19b['resident'])} B")
check("ramdisk entry byte-equal to the v19 entry", e19b["ramdisk"] == e19["ramdisk"], f"{len(e19b['ramdisk'])} B")
check("usb entry says 1", e19b["usb"] == b"1\0", repr(e19b["usb"]))
check("resident/ramdisk are APFS containers (NXSB @+32)",
      e19b["resident"][32:36] == b"NXSB" and e19b["ramdisk"][32:36] == b"NXSB")

print("[loader (v19b: the four Round 2 items)]")
ldr = e19b["loader.efi"]
check("loader.efi is the v19b build (9dc2f5db), not the v18 carry",
      sha(ldr).startswith("9dc2f5db") and ldr != e19["loader.efi"], sha(ldr)[:16])
check("item 1: the softened re-throw lines",
      all(s in ldr for s in (b"the re-throw is softened", b"kept its host: no re-throw")))
check("item 2: the stage-serving lines",
      all(s in ldr for s in (b"the bring-up is still arming (the run is next)",)))
check("item 3: the raw UsbFn code lines",
      b"through UsbFn (raw)" in ldr and b"the wall's raw code stays unknown" in ldr)
check("item 4: the settle is five seconds (the 25 s first-try line retired)",
      b"five quiet seconds before the first try" in ldr and
      b"twenty-five quiet seconds before the first try" not in ldr)
check("v18's mechanism kept: the present + probe + re-throw forensics",
      all(s in ldr for s in (b"the gadget is presented to the host (the pull-up is ours)",
                             b"usb: bulk probe gen %d beat %d: %x",
                             b"usb: the bulk pair answered: armed at generation %d, beat %d",
                             b"the pair never armed across 3 generations",
                             b"the re-throw did not come back")))
check("v18's DWC3 wake kept", b"usb: dwc3 woken (phy suspend off + core soft reset)" in ldr)
check("loader.efi carries the oem recording handler", b"oem recording" in ldr and b"no recording" in ldr)
check("loader.efi keeps the d22ap identity", b"D22AP" in ldr and b"iPhone10,3" in ldr)

# F10 pin: entry RVA must still hold, and the XNUP movk must be followed by the 0xF4000000 movz
# (layout-robust: the patch moved code, so the absolute RVA of the pair is re-derived here).
_off = struct.unpack_from("<I", ldr, 0x3C)[0]
_epi = struct.unpack_from("<I", ldr, _off + 24 + 16)[0]
check("loader entry at RVA 0x2140", _epi == 0x2140, hex(_epi))
_m = ldr.find(struct.pack("<I", 0x72AA0AB3))
check("PAYLOAD_BASE=0xF4000000 pin (XNUP movk 0x72AA0AB3 followed by the movz 0x52BE8008)",
      _m >= 0 and struct.unpack_from("<I", ldr, _m + 8)[0] == 0x52BE8008)
_sect = _off + 24 + struct.unpack_from("<H", ldr, _off + 20)[0]
_nsec = struct.unpack_from("<H", ldr, _off + 6)[0]
_tva = _tpraw = None
for _i in range(_nsec):
    _s = ldr[_sect + 40*_i: _sect + 40*_i + 40]
    if _s[:5] == b".text":
        _tvs, _tva, _trs, _tpraw = struct.unpack_from("<IIII", _s[8:24])
        break
check(".text section found", _tva is not None)
_rva = _m + _tva - _tpraw
check("the pin's real RVA is reported for the record", _rva > 0, hex(_rva))
check("loader is the dual-ramdisk/resident build",
      b"RAMDisk1" in ldr and b"may be written this run" in ldr)

print("[graft]")
fm, fver, _, orig, voff, vsz = struct.unpack_from(">4sIIQQQ", img, len(img) - 64)
check("footer AVBf v1.0", fm == b"AVBf" and fver == 1)
check("orig_size == vbmeta_offset == content end", orig == voff == content_end, f"{voff}")
vb = img[voff:voff + vsz]
check("vbmeta size 2432", vsz == 2432)
stock_vb_off = struct.unpack_from(">Q", stock, len(stock) - 64 + 20)[0]
stock_vb_size = struct.unpack_from(">Q", stock, len(stock) - 64 + 28)[0]
check("vbmeta == stock bytes @stock footer offset",
      vb == stock[stock_vb_off:stock_vb_off + stock_vb_size])
check("zero fill between vbmeta end and footer",
      img[voff + vsz:len(img) - 64] == b"\0" * (len(img) - 64 - voff - vsz))
check("final size 192 MiB", len(img) == 201326592)

print(f"\nALL {ok} CHECKS PASSED")
print("final sha256:", sha(img))
