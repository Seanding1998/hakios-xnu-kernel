#!/usr/bin/env python3
"""Wave 23 verification of udon-hakios-grafted-v19.img (virtual-display evidence round).

Shape identical to wave22-scripts/verify-udon-hakios-v18.py, with the v18 mechanism kept
whole (loader 553289a4: pump-forward + self-present + the v17b probe stage byte-identical)
and the Wave 23 cmdline-only moves asserted on top:
  - loader/kernel/kernel.ver/resident/ramdisk/usb entries are the V18 payload's bytes,
    byte for byte (cmdline-only round: nothing else moves);
  - the cmdline entry is the NEW v19 bytes: rec_secs=280 rec_ring=1 rec_mb=256 +
    loader_return_after=300; en0_addr traded away for the 607 composed cap (T1 finding:
    the loader prepends a 110-character head -- ground truth logdump-v18.bin @83231 is a
    581-character composed v15-era line = 110 + 471; 488 + 110 = 598 < 607);
  - the F10 pin (PAYLOAD_BASE=0xF4000000 double layer) re-asserted on the carried loader;
  - FD (8924cb67) and shim (108ce972) untouched.

usage: verify-udon-hakios-v19.py IMG STOCK SHIM FD PAYLOAD_V19 PAYLOAD_V18 CMDLINE_V19 KERNEL_FILE
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD_V19, PAYLOAD_V18, CMDLINE_V19, KFILE = sys.argv[1:9]

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
payload = open(PAYLOAD_V19, "rb").read()
payload_v18 = open(PAYLOAD_V18, "rb").read()
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
check("cmdline = v19 file bytes exactly", g[cmd_off:cmd_off + cmd_sz] == cmdline_v19)
check("cmdline ends with rec_mb=256 (the recording block is the last word)",
      cmd.endswith("rec_secs=280 rec_ring=1 rec_mb=256"))
check("recording args present exactly once",
      cmd.count("rec_secs=280") == 1 and cmd.count("rec_ring=1") == 1 and cmd.count("rec_mb=256") == 1)
check("loader_return_after=300 (the SpringBoard window; F6's vnode cliff is accepted)",
      cmd.count("loader_return_after=300") == 1 and cmd.count("loader_return_after=180") == 0)
check("en0_addr is gone (the 607 composed cap; the loader USB channel serves this round)",
      "en0_addr" not in cmd)
check("v18's other bytes kept: touchscreen/buttons/ufs/root/hw_target/soc set intact",
      all(a in cmd for a in ("touchscreen=1", "buttons=1", "buttons_map=1", "buttons_core=0xc400000",
                             "buttons_cnfg=0xc42d000", "buttons_obs=0xc440000",
                             "cpus=8", "bootcpu=7", "small_cores_after=0", "serial=0",
                             "soc_rsc=0x17a20000", "soc_ipa_fw=ipa_fws", "ufs=2", "ufs_write=1",
                             "var_hfs=ufs_darwin_data", "root_apfs=ufs_darwin", "hw_target=D22ap")))
check("no ufs_check (retired in v14)", cmd.count("ufs_check") == 0)
check("cmdline budget: composed = payload(488) + measured head(110) = 598 < 607",
      len(cmd) == 488 and len(cmd) + 110 < 607, f"{len(cmd)}+110={len(cmd)+110}")
check("cmdline budget hard bound: even the v18 verify's conservative +122 estimate is reported",
      len(cmd) + 110 < 607, f"conservative {len(cmd)+122} {'<' if len(cmd)+122 < 608 else '>='} 608 (measured head governs)")

def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e19 = payload_entries(payload)
e18 = payload_entries(payload_v18)
print("[entries]")
check("kernel == the v15/v16 build carried by v18, byte for byte",
      e19["kernel"] == kfile == e18["kernel"], f"sha256 {sha(e19['kernel'])[:16]}")
check("kernel carries the Mini display + surface drivers (the stack under test)",
      all(s in e19["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",
                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u",
                                       b"recording %u s of the screen")))
check("kernel carries the recording boot-arg tunables (rec_secs/rec_mb/rec_ring)",
      all(s in e19["kernel"] for s in (b"rec_secs", b"rec_mb", b"rec_ring", b"rec_step")))
check("kernel keeps the en0 driver code (only its cmdline switch is off this round)",
      b"en0_addr" in e19["kernel"] and b"10.0.0.2/30" in e19["kernel"])
check("kernel keeps the s3910 TouchComm driver", b"TouchComm v" in e19["kernel"])
check("kernel.ver byte-equal to the v18 entry", e19["kernel.ver"] == e18["kernel.ver"], sha(e19["kernel.ver"])[:16])
check("kernel.ver is the afd473f5 stamp", sha(e19["kernel.ver"]).startswith("afd473f5"), sha(e19["kernel.ver"])[:16])
check("resident entry byte-equal to the v18 entry (darwin front untouched)",
      e19["resident"] == e18["resident"], f"{len(e19['resident'])} B")
check("ramdisk entry byte-equal to the v18 entry", e19["ramdisk"] == e18["ramdisk"], f"{len(e19['ramdisk'])} B")
check("usb entry says 1", e19["usb"] == b"1\0", repr(e19["usb"]))
check("resident is an APFS container (NXSB @+32)", e19["resident"][32:36] == b"NXSB")
check("ramdisk is an APFS container (NXSB @+32)", e19["ramdisk"][32:36] == b"NXSB")

print("[loader (carried, not rebuilt)]")
ldr = e19["loader.efi"]
check("loader.efi is the v18 build (553289a4), byte-identical to the v18 payload's entry",
      e19["loader.efi"] == e18["loader.efi"] and sha(ldr).startswith("553289a4"), sha(ldr)[:16])
check("loader.efi carries the v17b probe forensics prints (mechanism kept whole)",
      all(s in ldr for s in (b"usb: bulk probe gen %d beat %d: %x",
                             b"usb: the bulk pair answered: armed at generation %d, beat %d",
                             b"the pair never armed across 3 generations",
                             b"the pair is un-armed after generation %d (last %x)",
                             b"twenty-five quiet seconds before the re-throw's try",
                             b"the re-throw did not come back")))
check("loader.efi carries Wave 22's self-presentation print",
      b"the gadget is presented to the host (the pull-up is ours)" in ldr)
check("loader.efi keeps the v16c DWC3 wake underneath the stage",
      b"usb: dwc3 woken (phy suspend off + core soft reset)" in ldr)
check("loader.efi carries the oem recording handler (the extraction command)",
      b"oem recording" in ldr and b"no recording" in ldr)
check("loader.efi carries the d22ap identity (D22AP + iPhone10,3)",
      all(s in ldr for s in (b"D22AP", b"iPhone10,3")))

# F10 pin (Boot #31): re-asserted on the carried loader bytes.
_off = struct.unpack_from("<I", ldr, 0x3C)[0]
_epi = struct.unpack_from("<I", ldr, _off + 24 + 16)[0]
check("loader entry at RVA 0x2140", _epi == 0x2140, hex(_epi))
_sect = _off + 24 + struct.unpack_from("<H", ldr, _off + 20)[0]
_nsec = struct.unpack_from("<H", ldr, _off + 6)[0]
_tva = _tpraw = None
for _i in range(_nsec):
    _s = ldr[_sect + 40*_i: _sect + 40*_i + 40]
    if _s[:5] == b".text":
        _tvs, _tva, _trs, _tpraw = struct.unpack_from("<IIII", _s[8:24])
        break
check(".text section found", _tva is not None)
check("loader carries PAYLOAD_BASE=0xF4000000 at the entry parse "
      "(movz 0x52BE8008 @0x2198 after movk 0x72AA0AB3 @0x2190)",
      struct.unpack_from("<I", ldr, 0x2198 - _tva + _tpraw)[0] == 0x52BE8008 and
      struct.unpack_from("<I", ldr, 0x2190 - _tva + _tpraw)[0] == 0x72AA0AB3)
_m = ldr.find(struct.pack("<I", 0x72AA0AB3))
check("layout-robust PAYLOAD_BASE pin (XNUP movk followed by the 0xF4000000 movz)",
      _m >= 0 and struct.unpack_from("<I", ldr, _m + 8)[0] == 0x52BE8008)
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
