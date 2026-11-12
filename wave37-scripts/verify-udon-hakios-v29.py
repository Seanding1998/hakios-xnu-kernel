#!/usr/bin/env python3
"""
Wave 37 (v29 = v28 + the cape-gpucc kernel c2ea0ca2 + the step-3 walk cmdline: gpu=1 +
adreno=3, 487 B). Everything else carried.

Wave 37 (v28 = v27 + the cape-gcc kernel e3852a0f: the sc7280 gcc offsets replaced by this
phone's cape values, gcc block map grown to the DTB's 0x1f4200). The cmdline stays the v27
probe cmdline (492 B). Everything else carried.
Wave 37 (v28 = v26 + the step-1 probe cmdline: + " adreno_only=1" inside the string)
verification of udon-hakios-grafted-v27.img.

Shape identical to the v26 verifies, with:
  - the cmdline = the v26 characters + " adreno_only=1" + one NUL (492 B, 491 chars,
    combined budget 110+491=601/607; adreno_fine deliberately left out -- inert under the
    gpu=1 path (pause_ms=0) and its 14 chars would truncate the 497-char payload cmdline
    budget);
  - the payload = the v26 bytes except the cmdline entry (kernel a39c931c, ramdisk 156b5be1,
    loader 0ade78b5, resident/kernel.ver/usb carried);
  - FD (8924cb67) and shim (108ce972) untouched, as every graft since wave 21.

usage: verify-udon-hakios-v29.py IMG STOCK SHIM FD PAYLOAD_V27 PAYLOAD_V26 CMDLINE_FILE KERNEL_FILE ROOT_APFS
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD_V29, PAYLOAD_V28, CMDLINE_FILE, KFILE, ROOT_APFS = sys.argv[1:10]

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
NULB = bytes([0])  # the single byte that terminates the kernel's command line
payload = open(PAYLOAD_V29, "rb").read()
payload_prev = open(PAYLOAD_V28, "rb").read()
root_apfs = open(ROOT_APFS, "rb").read()
cmdline_file = open(CMDLINE_FILE, "rb").read()

def _payload_cmdline(path):
    _d = open(path, "rb").read()
    _m, _s = struct.unpack_from("<II", _d, 0)
    _off = 8
    while _off + 24 <= 8 + _s:
        _name = _d[_off:_off + 16].split(b"\0")[0].decode()
        if not _name:
            break
        _esz, _ = struct.unpack_from("<II", _d, _off + 16)
        _off += 24
        if _name == "cmdline":
            return _d[_off:_off + _esz]
        _off += (_esz + 15) // 16 * 16
    raise RuntimeError("no cmdline entry")
eprev_cmd = _payload_cmdline(PAYLOAD_V28)
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
check("cmdline = the v28 characters with the walk arg (gpu=1 + adreno=3, NUL at the tail)",
      g[cmd_off:cmd_off + cmd_sz] == cmdline_file and cmdline_file == eprev_cmd.split(NULB)[0].replace(b" adreno_only=1", b" adreno=3") + NULB)
check("cmdline carries loader_return_after=600, gpu=1, adreno=3 (all before the NUL)",
      cmd.count("loader_return_after=600") == 1 and cmd.count("gpu=1") == 1 and
      cmd.count("adreno=3") == 1 and cmd.count("loader_return_after=1800") == 0 and
      cmd.count("en0_addr=10.0.0.2") == 1)
check("cmdline carries no adreno_only and no adreno_fine (the walk arg is adreno=3)",
      "adreno_only" not in cmd and "adreno_fine" not in cmd)
check("cmdline carries no recording boot-args (the display rounds stay out)",
      all(s not in cmd for s in ("rec_secs", "rec_mb", "rec_ring")))
check("cmdline is 486 chars (combined budget 110+486=596/607: no truncation)", len(cmd) == 486)

def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e29 = payload_entries(payload)
eprev = payload_entries(payload_prev)
print("[entries]")
check("kernel == the passed kernel file (the wave 37 cape-gpucc build; differs from v28's)",
      e29["kernel"] == kfile and not sha(e29["kernel"]).startswith("e3852a0f"),
      f"sha256 {sha(e29['kernel'])[:16]} (v28's was e3852a0f...)")
check("kernel carries the gen7 parameter layer (the a730 names, the chip id, the log lines)",
      all(s in e29["kernel"] for s in (b"gmu_gen70000.bin", b"a730_sqe.fw", b"a730_zap.mdt",
                                       b"a730_zap.b01", b"an Adreno 730v3 (chip id 0x7030002)",
                                       b"tcm_ret_cntl", b"general_10")))
check("kernel still carries the Wave 26 feeder (carried, not under test)",
      all(s in e29["kernel"] for s in (b"the feeder is in: the ring",
                                       b"the stage has no room")))
check("kernel carries the Mini display + surface drivers (carried, not under test)",
      all(s in e29["kernel"] for s in (b"MiniIOMobileFramebuffer", b"MiniIOSurface",
                                       b"IOCoreSurfaceRoot", b"created surface %u: %ux%u")))
check("loader.efi == the v24 carry (0ade78b5, the maxvnodes build) byte for byte",
      e29["loader.efi"] == eprev["loader.efi"] and sha(e29["loader.efi"]).startswith("0ade78b5"),
      f"{sha(e29['loader.efi'])[:16]}")
check("loader carries the kern.maxvnodes DT injection (the vnode cap's bypass)",
      b"kern.maxvnodes" in e29["loader.efi"])
check("kernel.ver byte-equal to the v26 entry", e29["kernel.ver"] == eprev["kernel.ver"], f"{len(e29['kernel.ver'])} B")
check("resident entry byte-equal to the v26 entry", e29["resident"] == eprev["resident"], f"{len(e29['resident'])} B")
check("cmdline entry == the built v29 cmdline file", e29["cmdline"] == cmdline_file, f"{len(e29['cmdline'])} B")
check("usb entry byte-equal to the v26 entry", e29["usb"] == eprev["usb"], repr(e29["usb"]))
check("usb entry says 1", e29["usb"] == b"1\0", repr(e29["usb"]))
check("ramdisk byte-equal to the v28 entry (unchanged in v29)",
      e29["ramdisk"] == root_apfs == eprev["ramdisk"],
      f"sha256 {sha(e29['ramdisk'])[:16]} (was {sha(eprev['ramdisk'])[:16]})")
check("ramdisk carries the pulled a730 firmware (plain fw/: the bytes, not just the names)",
      b"gmu_gen70000.bin" in e29["ramdisk"] and b"a730_zap.mdt" in e29["ramdisk"])
check("ramdisk is a 4 MB APFS container (NXSB @+32)",
      len(e29["ramdisk"]) == 4194304 and e29["ramdisk"][32:36] == b"NXSB")
check("resident is an APFS container (NXSB @+32)", e29["resident"][32:36] == b"NXSB")

print("[loader (the Wave 26 maxvnodes build)]")
ldr = e29["loader.efi"]
check("item 1: the console mirror (the vendor door is the shim's SerialPort Lib, not ConOut)",
      all(s in ldr for s in (b"SerialPort Lib", b"the console mirror: vendor door %s, console door %s",
                             b"the vendor said '%s': the line is sticky now")))
check("item 1: the mirror leads list",
      all(s in ldr for s in (b"DEPSTARTCFG Fails", b"Failed to set config for ep",
                             b"DwcConfigureEP failed", b"Unknown USB Speed")))
check("item 2: the one event consumer",
      b"checkpoint-3: the standing receive finished" in ldr and b"the host left: the standing receive (gen %d) is retired" in ldr)
check("item 3: the standing receive + the gate",
      all(s in ldr for s in (b"checkpoint-1: the standing receive is in",
                             b"the first refusal is on the record",
                             b"refused %x again (x%d since the first")))
check("item 4: the state sampler (registers + the vendor fields behind the signature)",
      all(s in ldr for s in (b"sample %s: GCTL %x DCTL %x DSTS %x DALEPENA %x",
                             b"sample %s (vendor): speed %d (%s) phys[2] state %d maxpkt %d phys[3] state %d",
                             b"carries no 'usbf' below")))
check("item 4: the timeline",
      b"the bring-up begins (the Wave 24 timeline runs from here)" in ldr)
check("item 4: the GCTL reset cleared by hand (P1-1)",
      b"soft reset was still set after the wait: cleared by hand" in ldr)
check("item 4: the raw look moved to the failure window's end",
      b"the raw UsbFn look (gen %d, a second submit by design)" in ldr and
      b"through UsbFn (raw)" not in ldr)
check("item 4: the buffer allocations split (P2-5)",
      b"the receive buffer alone (%x)" in ldr and b"the send buffer (%x); the receive buffer goes back" in ldr)
check("v19b's beat-0 raw look and the zero-length probe are retired",
      b"through UsbFn (raw)" not in ldr and b"USB->send(USB_EP_OUT, 0," not in ldr)
check("v18's mechanism kept: the present + armed + never-armed + re-throw forensics",
      all(s in ldr for s in (b"the gadget is presented to the host (the pull-up is ours)",
                             b"usb: the bulk pair answered: armed at generation %d, beat %d",
                             b"the pair never armed across 3 generations",
                             b"the re-throw did not come back",
                             b"kept its host: no re-throw")))
check("v18's DWC3 wake kept", b"usb: dwc3 woken (phy suspend off + core soft reset)" in ldr)
check("loader.efi carries the oem recording handler", b"oem recording" in ldr and b"no recording" in ldr)
check("loader.efi keeps the d22ap identity", b"D22AP" in ldr and b"iPhone10,3" in ldr)

# F10 pin: entry RVA must still hold, and PAYLOAD_BASE must be built in (this build's
# arrangement: movz #0xF400,lsl#16 within 6 instructions of the XNUP-magic movk #0x5055,lsl#16).
_off = struct.unpack_from("<I", ldr, 0x3C)[0]
_epi = struct.unpack_from("<I", ldr, _off + 24 + 16)[0]
check("loader entry at RVA 0x2140", _epi == 0x2140, hex(_epi))
_pin = None
for _m in range(0, len(ldr) - 40, 4):
    if struct.unpack_from("<I", ldr, _m)[0] == 0x52BE8008:      # movz w?, #0xF400, lsl #16
        for _k in range(1, 7):
            if struct.unpack_from("<I", ldr, _m + 4 * _k)[0] == 0x72AA0AB3:  # movk #0x5055, lsl #16
                _pin = (_m, _k)
                break
        if _pin:
            break
check("PAYLOAD_BASE=0xF4000000 pin (movz #0xF400 near the XNUP-magic movk #0x5055)", _pin is not None)
_sect = _off + 24 + struct.unpack_from("<H", ldr, _off + 20)[0]
_nsec = struct.unpack_from("<H", ldr, _off + 6)[0]
_tva = _tpraw = None
for _i in range(_nsec):
    _s = ldr[_sect + 40*_i: _sect + 40*_i + 40]
    if _s[:5] == b".text":
        _tvs, _tva, _trs, _tpraw = struct.unpack_from("<IIII", _s[8:24])
        break
check(".text section found", _tva is not None)
check("the pin's RVA is reported for the record",
      _pin is not None and (_pin[0] + _tva - _tpraw) > 0, hex(_pin[0] + _tva - _tpraw) if _pin else "-")
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
